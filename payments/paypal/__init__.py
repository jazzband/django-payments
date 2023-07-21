import json
import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP
from decimal import Decimal
from functools import wraps

import requests
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.utils import timezone
from requests.exceptions import HTTPError

from .. import PaymentError
from .. import PaymentStatus
from .. import RedirectNeeded
from ..core import BasicProvider
from ..core import get_credit_card_issuer
from .forms import PaymentForm

# Get an instance of a logger
logger = logging.getLogger(__name__)

CENTS = Decimal("0.01")


class UnauthorizedRequest(Exception):
    pass


def authorize(fun):
    @wraps(fun)
    def wrapper(*args, **kwargs):
        self = args[0]
        payment = args[1]
        self.access_token = self.get_access_token(payment)
        try:
            response = fun(*args, **kwargs)
        except HTTPError as e:
            if e.response.status_code == 401:
                last_auth_response = self.get_last_response(payment, is_auth=True)
                if "access_token" in last_auth_response:
                    del last_auth_response["access_token"]
                    self.set_response_data(payment, last_auth_response, is_auth=True)
                self.access_token = self.get_access_token(payment)
                response = fun(*args, **kwargs)
            else:
                raise
        return response

    return wrapper


class PaypalProvider(BasicProvider):
    """Payment provider for Paypal, redirection-based.

    This backend implements payments using `PayPal.com <https://www.paypal.com/>`_.

    :param client_id: Client ID assigned by PayPal or your email address
    :param secret: Secret assigned by PayPal
    :param endpoint: The API endpoint to use. For the production environment, use ``'https://api.paypal.com'`` instead
    :param capture: Whether to capture the payment automatically. See :ref:`capture-payments` for more details.
    """

    def __init__(
        self,
        client_id,
        secret,
        endpoint="https://api.sandbox.paypal.com",
        capture=True,
        **kwargs,
    ):
        self.secret = secret
        self.client_id = client_id
        self.endpoint = endpoint
        self.oauth2_url = self.endpoint + "/v1/oauth2/token"
        self.payments_url = self.endpoint + "/v1/payments/payment"
        self.subscriptions_url = self.endpoint + "/v1/billing/subscriptions"
        self.plans_url = self.endpoint + "/v1/billing/plans"
        self.payment_execute_url = self.payments_url + "/%(id)s/execute/"
        self.payment_refund_url = (
            self.endpoint + "/v1/payments/capture/{captureId}/refund"
        )
        self.plan_id = kwargs.get("plan_id", None)
        super().__init__(capture=capture)

    def set_response_data(self, payment, response, is_auth=False):
        extra_data = json.loads(payment.extra_data or "{}")
        if is_auth:
            extra_data["auth_response"] = response
        else:
            extra_data["response"] = response
            if "links" in response:
                extra_data["links"] = {link["rel"]: link for link in response["links"]}
        payment.extra_data = json.dumps(extra_data)
        payment.save()

    def set_response_links(self, payment, response):
        transaction = response["transactions"][0]
        related_resources = transaction["related_resources"][0]
        resource_key = "sale" if self._capture else "authorization"
        links = related_resources[resource_key]["links"]
        extra_data = json.loads(payment.extra_data or "{}")
        extra_data["links"] = {link["rel"]: link for link in links}
        payment.extra_data = json.dumps(extra_data)
        payment.save()

    def set_error_data(self, payment, error):
        extra_data = json.loads(payment.extra_data or "{}")
        extra_data["error"] = error
        payment.extra_data = json.dumps(extra_data)
        payment.save()

    def _get_links(self, payment):
        extra_data = json.loads(payment.extra_data or "{}")
        links = extra_data.get("links", {})
        return links

    @authorize
    def post(self, payment, *args, **kwargs):
        kwargs["headers"] = {
            "Content-Type": "application/json",
            "Authorization": self.access_token,
        }
        if "data" in kwargs:
            kwargs["data"] = json.dumps(kwargs["data"])
        http_method = kwargs.pop("http_method", requests.post)
        response = http_method(*args, **kwargs)
        try:
            data = response.json()
        except ValueError:
            data = {}
        if 400 <= response.status_code <= 500:
            if payment:
                self.set_error_data(payment, data)
            logger.debug(data)
            message = "Paypal error"
            if response.status_code == 400:
                error_data = response.json()
                logger.warning(
                    message,
                    extra={"response": error_data, "status_code": response.status_code},
                )
                message = error_data.get("message", message)
            else:
                logger.warning(message, extra={"status_code": response.status_code})
            if payment:
                payment.change_status(PaymentStatus.ERROR, message)
            raise PaymentError(message)
        else:
            if payment:
                self.set_response_data(payment, data)
        return data

    def get(self, payment, *args, **kwargs):
        return self.post(payment, http_method=requests.get, *args, **kwargs)

    def get_last_response(self, payment, is_auth=False):
        extra_data = json.loads(payment.extra_data or "{}")
        if is_auth:
            return extra_data.get("auth_response", {})
        return extra_data.get("response", {})

    def get_access_token(self, payment):
        if payment:
            last_auth_response = self.get_last_response(payment, is_auth=True)
            created = payment.created
        else:
            last_auth_response = {}
        now = timezone.now()
        if (
            "access_token" in last_auth_response
            and "expires_in" in last_auth_response
            and (created + timedelta(seconds=last_auth_response["expires_in"])) > now
        ):
            return "{} {}".format(
                last_auth_response["token_type"], last_auth_response["access_token"]
            )
        else:
            headers = {"Accept": "application/json", "Accept-Language": "en_US"}
            post = {"grant_type": "client_credentials"}
            response = requests.post(
                self.oauth2_url,
                data=post,
                headers=headers,
                auth=(self.client_id, self.secret),
            )
            response.raise_for_status()
            data = response.json()
            last_auth_response.update(data)
            if payment:
                self.set_response_data(payment, last_auth_response, is_auth=True)
            return "{} {}".format(data["token_type"], data["access_token"])

    def get_transactions_items(self, payment):
        for purchased_item in payment.get_purchased_items():
            price = purchased_item.price.quantize(CENTS, rounding=ROUND_HALF_UP)
            item = {
                "name": purchased_item.name[:127],
                "quantity": str(purchased_item.quantity),
                "price": str(price),
                "currency": purchased_item.currency,
                "sku": purchased_item.sku,
            }
            yield item

    def get_transactions_data(self, payment):
        items = list(self.get_transactions_items(payment))
        sub_total = payment.total - payment.delivery - payment.tax
        sub_total = sub_total.quantize(CENTS, rounding=ROUND_HALF_UP)
        total = payment.total.quantize(CENTS, rounding=ROUND_HALF_UP)
        tax = payment.tax.quantize(CENTS, rounding=ROUND_HALF_UP)
        delivery = payment.delivery.quantize(CENTS, rounding=ROUND_HALF_UP)
        data = {
            "intent": "sale" if self._capture else "authorize",
            "transactions": [
                {
                    "amount": {
                        "total": str(total),
                        "currency": payment.currency,
                        "details": {
                            "subtotal": str(sub_total),
                            "tax": str(tax),
                            "shipping": str(delivery),
                        },
                    },
                    "item_list": {"items": items},
                    "description": payment.description,
                }
            ],
        }
        return data

    def get_redirect_urls(self, payment):
        return_url = self.get_return_url(payment)
        return {"return_url": return_url, "cancel_url": return_url}

    def get_product_data(self, payment, extra_data=None):
        data = self.get_transactions_data(payment)
        data["redirect_urls"] = self.get_redirect_urls(payment)
        data["payer"] = {"payment_method": "paypal"}
        return data

    def get_form(self, payment, data=None):
        if not payment.id:
            payment.save()
        links = self._get_links(payment)
        redirect_to = links.get("approval_url")
        if not redirect_to:
            if payment.is_recurring():
                payment_data = self.create_subscription(payment)
                links = self._get_links(payment)
                redirect_to = links["approve"]
            else:
                payment_data = self.create_payment(payment)
                links = self._get_links(payment)
                redirect_to = links["approval_url"]
            payment.transaction_id = payment_data["id"]
        payment.change_status(PaymentStatus.WAITING)
        raise RedirectNeeded(redirect_to["href"])

    def process_data(self, payment, request):
        success_url = payment.get_success_url()
        failure_url = payment.get_failure_url()
        if "token" not in request.GET:
            return HttpResponseForbidden("FAILED")
        if payment.is_recurring():
            self.process_subscription_data(payment, request)
        payer_id = request.GET.get("PayerID")
        if not payer_id:
            if payment.status != PaymentStatus.CONFIRMED:
                payment.change_status(PaymentStatus.REJECTED)
                return redirect(failure_url)
            else:
                return redirect(success_url)
        try:
            executed_payment = self.execute_payment(payment, payer_id)
        except PaymentError:
            return redirect(failure_url)
        self.set_response_links(payment, executed_payment)
        payment.attrs.payer_info = executed_payment["payer"]["payer_info"]
        if self._capture:
            payment.captured_amount = payment.total
            payment.change_status(PaymentStatus.CONFIRMED)
        else:
            payment.change_status(PaymentStatus.PREAUTH)
        return redirect(success_url)

    def process_subscription_data(self, payment, request):
        success_url = payment.get_success_url()
        failure_url = payment.get_failure_url()
        subscription_id = request.GET.get("subscription_id")
        if not subscription_id:
            if payment.status != PaymentStatus.CONFIRMED:
                payment.change_status(PaymentStatus.REJECTED)
                return redirect(failure_url)
            else:
                return redirect(success_url)
        try:
            subscription_data = self.get_subscription(payment)
        except PaymentError:
            return redirect(failure_url)
        if subscription_data["status"] == "ACTIVE":
            payment.captured_amount = payment.total
            payment.change_status(PaymentStatus.CONFIRMED)
            return redirect(success_url)
        payment.change_status(PaymentStatus.REJECTED)
        return redirect(failure_url)

    def create_subscription(self, payment, extra_data=None):
        redirect_urls = self.get_redirect_urls(payment)
        if callable(self.plan_id):
            plan_id = self.plan_id(payment)
        else:
            plan_id = self.plan_id
        plan_data = {
            "plan_id": plan_id,
            "plan": {  # Override plan values
                "billing_cycles": [
                    {
                        "sequence": 1,
                        # TODO: This doesn't work:
                        # "frequency": {
                        #     "interval_unit": payment.get_subscription().get_unit(),
                        #     "interval_count": payment.get_subscription().get_period(),
                        # },
                        "pricing_scheme": {
                            "fixed_price": {
                                "currency_code": payment.currency,
                                "value": str(
                                    payment.total.quantize(
                                        CENTS, rounding=ROUND_HALF_UP
                                    )
                                ),
                            },
                        },
                    }
                ],
            },
            "application_context": {
                "shipping_preference": "NO_SHIPPING",
                "user_action": "SUBSCRIBE_NOW",
                "payment_method": {
                    "payer_selected": "PAYPAL",
                    "payee_preferred": "IMMEDIATE_PAYMENT_REQUIRED",
                },
                **redirect_urls,
            },
        }
        payment_data = self.post(payment, self.subscriptions_url, data=plan_data)
        subscription = payment.get_subscription()
        subscription.set_recurrence(payment_data["id"])
        return payment_data

    def cancel_subscription(self, subscription):
        subscription_id = subscription.get_token()
        self.post(None, f"{self.subscriptions_url}/{subscription_id}/cancel")

    def create_payment(self, payment, extra_data=None):
        product_data = self.get_product_data(payment, extra_data)
        payment = self.post(payment, self.payments_url, data=product_data)
        return payment

    def execute_payment(self, payment, payer_id):
        post = {"payer_id": payer_id}
        links = self._get_links(payment)
        execute_url = links["execute"]["href"]
        return self.post(payment, execute_url, data=post)

    def get_subscription(self, payment):
        links = self._get_links(payment)
        execute_url = links["edit"]["href"]
        return self.get(payment, execute_url)

    def get_amount_data(self, payment, amount=None):
        return {
            "currency": payment.currency,
            "total": str(amount.quantize(CENTS, rounding=ROUND_HALF_UP)),
        }

    def capture(self, payment, amount=None):
        if amount is None:
            amount = payment.total
        amount_data = self.get_amount_data(payment, amount)
        capture_data = {"amount": amount_data, "is_final_capture": True}
        links = self._get_links(payment)
        url = links["capture"]["href"]
        try:
            capture = self.post(payment, url, data=capture_data)
        except HTTPError as e:
            try:
                error = e.response.json()
            except ValueError:
                error = {}
            if error.get("name") != "AUTHORIZATION_ALREADY_COMPLETED":
                raise e
            capture = {"state": "completed"}
        state = capture["state"]
        if state == "completed":
            payment.change_status(PaymentStatus.CONFIRMED)
            return amount
        elif state in ["partially_captured", "partially_refunded"]:
            return amount
        elif state == "pending":
            payment.change_status(PaymentStatus.WAITING)
        elif state == "refunded":
            payment.change_status(PaymentStatus.REFUNDED)
            raise PaymentError("Payment already refunded")

    def release(self, payment):
        links = self._get_links(payment)
        url = links["void"]["href"]
        self.post(payment, url)

    def refund(self, payment, amount=None):
        if amount is None:
            amount = payment.captured_amount
        amount_data = self.get_amount_data(payment, amount)
        refund_data = {"amount": amount_data}
        links = self._get_links(payment)
        url = links["refund"]["href"]
        self.post(payment, url, data=refund_data)
        payment.change_status(PaymentStatus.REFUNDED)
        return amount


class PaypalCardProvider(PaypalProvider):
    """Payment provider for Paypal, form-based.

    This backend implements payments using `PayPal.com <https://www.paypal.com/>`_ but
    the credit card data is collected by your site.

    Parameters are the same as  :class:`~PaypalProvider`.

    This backend does not support fraud detection.
    """

    def get_form(self, payment, data=None):
        if payment.status == PaymentStatus.WAITING:
            payment.change_status(PaymentStatus.INPUT)
        form = PaymentForm(data, provider=self, payment=payment)
        if form.is_valid():
            raise RedirectNeeded(payment.get_success_url())
        return form

    def get_product_data(self, payment, extra_data=None):
        extra_data = extra_data or {}
        data = self.get_transactions_data(payment)
        year = extra_data["expiration"].year
        month = extra_data["expiration"].month
        number = extra_data["number"]
        card_type, _card_issuer = get_credit_card_issuer(number)
        credit_card = {
            "number": number,
            "type": card_type,
            "expire_month": month,
            "expire_year": year,
        }
        if "cvv2" in extra_data and extra_data["cvv2"]:
            credit_card["cvv2"] = extra_data["cvv2"]
        data["payer"] = {
            "payment_method": "credit_card",
            "funding_instruments": [{"credit_card": credit_card}],
        }
        return data

    def process_data(self, payment, request):
        return HttpResponseForbidden("FAILED")
