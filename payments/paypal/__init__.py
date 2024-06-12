from __future__ import annotations

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

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded
from payments.core import BasicProvider
from payments.core import get_credit_card_issuer

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
    :param endpoint: The API endpoint to use. For the production environment,
        use ``'https://api.paypal.com'`` instead
    :param capture: Whether to capture the payment automatically.
        See :ref:`capture-payments` for more details.
    """

    def __init__(
        self, client_id, secret, endpoint="https://api.sandbox.paypal.com", capture=True
    ):
        self.secret = secret
        self.client_id = client_id
        self.endpoint = endpoint
        self.oauth2_url = self.endpoint + "/v1/oauth2/token"
        self.payments_url = self.endpoint + "/v1/payments/payment"
        self.payment_execute_url = self.payments_url + "/%(id)s/execute/"
        self.payment_refund_url = (
            self.endpoint + "/v1/payments/capture/{captureId}/refund"
        )
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
        return extra_data.get("links", {})

    @authorize
    def post(self, payment, *args, **kwargs):
        kwargs["headers"] = {
            "Content-Type": "application/json",
            "Authorization": self.access_token,
        }
        if "data" in kwargs:
            kwargs["data"] = json.dumps(kwargs["data"])
        response = requests.post(*args, **kwargs)
        try:
            data = response.json()
        except ValueError:
            data = {}
        if 400 <= response.status_code <= 500:
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
            payment.change_status(PaymentStatus.ERROR, message)
            raise PaymentError(message)
        self.set_response_data(payment, data)
        return data

    def get_last_response(self, payment, is_auth=False):
        extra_data = json.loads(payment.extra_data or "{}")
        if is_auth:
            return extra_data.get("auth_response", {})
        return extra_data.get("response", {})

    def get_access_token(self, payment):
        last_auth_response = self.get_last_response(payment, is_auth=True)
        created = payment.created
        now = timezone.now()
        if (
            "access_token" in last_auth_response
            and "expires_in" in last_auth_response
            and (created + timedelta(seconds=last_auth_response["expires_in"])) > now
        ):
            return "{} {}".format(
                last_auth_response["token_type"], last_auth_response["access_token"]
            )
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
        return {
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

    def get_product_data(self, payment, extra_data=None):
        return_url = self.get_return_url(payment)
        data = self.get_transactions_data(payment)
        data["redirect_urls"] = {"return_url": return_url, "cancel_url": return_url}
        data["payer"] = {"payment_method": "paypal"}
        return data

    def get_form(self, payment, data=None):
        if not payment.id:
            payment.save()
        links = self._get_links(payment)
        redirect_to = links.get("approval_url")
        if not redirect_to:
            payment_data = self.create_payment(payment)
            payment.transaction_id = payment_data["id"]
            links = self._get_links(payment)
            redirect_to = links["approval_url"]
        payment.change_status(PaymentStatus.WAITING)
        raise RedirectNeeded(redirect_to["href"])

    def process_data(self, payment, request):
        success_url = payment.get_success_url()
        failure_url = payment.get_failure_url()
        if "token" not in request.GET:
            return HttpResponseForbidden("FAILED")
        payer_id = request.GET.get("PayerID")
        if not payer_id:
            if payment.status != PaymentStatus.CONFIRMED:
                payment.change_status(PaymentStatus.REJECTED)
                return redirect(failure_url)
            return redirect(success_url)
        try:
            executed_payment = self.execute_payment(payment, payer_id)
        except PaymentError:
            return redirect(failure_url)
        self.set_response_links(payment, executed_payment)
        payment.attrs.payer_info = executed_payment["payer"]["payer_info"]
        if self._capture:
            payment.captured_amount = payment.total
            type(payment).objects.filter(pk=payment.pk).update(
                captured_amount=payment.captured_amount
            )
            payment.change_status(PaymentStatus.CONFIRMED)
        else:
            payment.change_status(PaymentStatus.PREAUTH)
        return redirect(success_url)

    def create_payment(self, payment, extra_data=None):
        product_data = self.get_product_data(payment, extra_data)
        return self.post(payment, self.payments_url, data=product_data)

    def execute_payment(self, payment, payer_id):
        post = {"payer_id": payer_id}
        links = self._get_links(payment)
        execute_url = links["execute"]["href"]
        return self.post(payment, execute_url, data=post)

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
        if state in ["partially_captured", "partially_refunded"]:
            return amount
        if state == "pending":
            payment.change_status(PaymentStatus.WAITING)
            return None
        if state == "refunded":
            payment.change_status(PaymentStatus.REFUNDED)
            raise PaymentError("Payment already refunded")
        return None

    def release(self, payment):
        links = self._get_links(payment)
        url = links["void"]["href"]
        self.post(payment, url)

    def refund(self, payment, amount=None):
        refund_data = {}
        if amount is not None:
            refund_data["amount"] = self.get_amount_data(payment, amount)
        links = self._get_links(payment)
        url = links["refund"]["href"]
        response = self.post(payment, url, data=refund_data)
        payment.change_status(PaymentStatus.REFUNDED)
        if response["amount"]["currency"] != payment.currency:
            raise NotImplementedError(
                f"refund's currency other than {payment.currency} not supported yet: "
                f"{response['amount']['currency']}"
            )
        return Decimal(response["amount"]["total"])


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
        if extra_data.get("cvv2"):
            credit_card["cvv2"] = extra_data["cvv2"]
        data["payer"] = {
            "payment_method": "credit_card",
            "funding_instruments": [{"credit_card": credit_card}],
        }
        return data

    def process_data(self, payment, request):
        return HttpResponseForbidden("FAILED")
