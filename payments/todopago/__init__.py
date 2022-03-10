from decimal import Decimal
from uuid import uuid4

from django.http import HttpRequest
from django.shortcuts import redirect
from python_todopago import TodoPagoConnector
from python_todopago.helpers import Item

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded
from payments.core import BasicProvider
from payments.models import BasePayment

STATUS_MAP = {
    "APROBADA": PaymentStatus.CONFIRMED,
}


class TodoPagoProvider(BasicProvider):
    """This backend implements payments using `TodoPago <https://todopago.com.ar/>`_.
    You'll need to install with extra dependencies to use this::

        pip install "django-payments[todopago]"

    :param token: The token provided by TP
    :param merchant: The merchant ID provided by TP
    :param sandbox: Whether to use sandbox mode.
    """

    def __init__(self, token: str, merchant: str, sandbox: bool):
        self.client = TodoPagoConnector(token, merchant, sandbox=sandbox)
        self.sandbox = sandbox

    def authorize_operation(self, payment: BasePayment):
        transaction_id = uuid4().hex
        authorization = self.client.authorize_operation(
            success_url=self.get_return_url(payment),
            failure_url=self.get_return_url(payment),
            operation_id=transaction_id,
            currency=payment.currency,
            amount=payment.total,
            city=payment.billing_city,
            country_code=payment.billing_country_code,
            state_code=payment.billing_country_area,
            billing_first_name=payment.billing_first_name,
            billing_last_name=payment.billing_last_name,
            billing_email=payment.billing_email,
            billing_phone=str(payment.billing_phone),
            billing_postcode=payment.billing_postcode,
            billing_address_1=payment.billing_address_1,
            billing_address_2=payment.billing_address_2,
            customer_id=payment.pk,
            customer_ip_address=payment.customer_ip_address,
            items=[
                Item(
                    item.name,
                    item.name,
                    item.sku,
                    item.price,
                    item.quantity,
                    round(item.price * Decimal(item.quantity)),
                )
                for item in payment.get_purchased_items()
            ],
        )

        if authorization.status_code != -1:
            raise PaymentError(
                message=f"Failed to authorize TodoPago operation. [{authorization.status_message}]",
                code=authorization.status_code,
                gateway_message=authorization.status_message,
            )

        payment.attrs.request_key = authorization.request_key
        payment.attrs.public_request_key = authorization.public_request_key
        payment.attrs.form_url = authorization.form_url

        payment.transaction_id = transaction_id
        payment.save()

        return authorization

    def fetch_operation_status(self, payment: BasePayment):
        request_key = payment.attrs.request_key
        answer_key = payment.attrs.answer_key

        status = self.client.get_operation_status(request_key, answer_key)

        if status.status_code != -1:
            message = "TodoPago didn't approve the payment."
            payment.change_status(PaymentStatus.ERROR, message)
            raise (PaymentError(message))

        upstream_status = status.status_message
        payment.change_status(STATUS_MAP[upstream_status])

    def get_action(self, payment: BasePayment):
        # This is the form-action. But we don't use a form.
        raise NotImplementedError()

    def process_callback(self, payment: BasePayment, request: HttpRequest):
        """Process TodoPago's callback.

        After a payment is made, TodoPago sends a GET request with the
        answer key. We use this to get the status of the payment.

        If there's no answer key then we assume that the payment failed.
        """
        answer_key = request.GET.get("Answer", None)
        if not answer_key:
            payment.change_status(PaymentStatus.ERROR)
            return redirect(payment.get_failure_url())

        payment.attrs.answer_key = answer_key
        payment.save()

        self.fetch_operation_status(payment)

        return redirect(payment.get_success_url())

    def process_data(self, payment: BasePayment, request: HttpRequest):
        """Handle a request received after a payment.

        If it's a GET request, then it's the user being redirected after
        completing a payment (it may have failed or have been successfull).

        TodoPago doesn't send POST requests, at least for now.
        If the payment is refunded from the TodoPago's platform there's no way
        we notice that.
        """
        if request.method == "GET":
            return self.process_callback(payment, request)

    def get_form(self, payment: BasePayment, data=None):
        if not hasattr(payment.attrs, "form_url"):
            _ = self.authorize_operation(payment)

        url = payment.attrs.form_url

        raise RedirectNeeded(url)

    def capture(self, payment: BasePayment, amount=None):
        raise NotImplementedError()

    def refund(self, payment: BasePayment, amount=None):
        raise NotImplementedError()
