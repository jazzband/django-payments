from decimal import Decimal
from uuid import uuid4

from python_todopago import TodoPagoConnector
from python_todopago.helpers import Item

from payments.core import BasicProvider
from payments.models import BasePayment


class TodoPagoProvider(BasicProvider):
    """This backend implements payments using `TodoPago <https://todopago.com.ar/>`_.
    You'll need to install with extra dependencies to use this::

        pip install "django-payments[todopago]"

    :param token: The token provided by TP
    :param merchant: The merchant ID provided by TP
    :param sandbox: Whether to use sandbox more.
    """

    def __init__(self, token: str, merchant: str, sandbox: bool):
        self.client = TodoPagoConnector(token, merchant, sandbox=sandbox)
        self.sandbox = sandbox

    def autorize_operation(self, payment: BasePayment):
        transaction_id = uuid4().hex
        authorization = self.client.authorize_operation(
            success_url=self.get_return_url(payment),
            failure_url=self.get_return_url(payment),
            operation_id=transaction_id,
            currency=int(payment.currency),
            amount=payment.total,
            city=payment.billing_city,
            country_code=payment.billing_country_code,
            state_code="D",  # TODO: add state code to payment model
            billing_first_name=payment.billing_first_name,
            billing_last_name=payment.billing_last_name,
            billing_email=payment.billing_email,
            billing_phone="+543513000000",  # TODO: add phone to payment model
            billing_postcode=payment.billing_postcode,
            billing_address_1=payment.billing_address_1,
            billing_address_2=payment.billing_address_2,
            customer_id="1",
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

        if authorization.status_code == -1:
            payment.attrs.request_key = authorization.request_key
            payment.attrs.public_request_key = authorization.public_request_key

            payment.transaction_id = transaction_id
            payment.save()

        return authorization
