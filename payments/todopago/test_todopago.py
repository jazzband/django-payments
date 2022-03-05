from typing import Optional
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from python_todopago.helpers import Authorization
from python_todopago.helpers import OperationStatus

from payments import PaymentStatus
from payments import PurchasedItem
from payments.todopago import TodoPagoProvider


class Payment(Mock):
    id = 1
    description = "payment"
    currency = "ARS"
    status = PaymentStatus.WAITING
    message = None
    total = 100
    transaction_id: Optional[str] = None
    billing_first_name = "John"
    billing_last_name = "Doe"
    billing_address_1 = "Some Address"
    billing_address_2 = "Some Address"
    billing_postcode = "12345"
    billing_city = "Some City"
    billing_country_code = "AR"
    billing_country_area = "Capital Federal"
    billing_phone = "+543513840247"
    customer_ip_address = "192.168.0.1"
    billing_email = "john@doe.com"

    def change_status(self, status, message=""):
        self.status = status
        self.message = message

    def change_fraud_status(self, status, message="", commit=True):
        self.fraud_status = status
        self.fraud_message = message

    def get_success_url(self):
        return "http://example.com/success"

    def get_failure_url(self):
        return "http://example.com/failure"

    def get_process_url(self):
        return "http://example.com/process"

    def get_purchased_items(self):
        yield PurchasedItem(
            name="Some Product",
            sku="SP12",
            quantity=1,
            price=100,
            currency="ARS",
        )


@pytest.fixture
def tp_provider():
    return TodoPagoProvider(
        "PRISMA f3d8b72c94ab4a06be2ef7c95490f7d3", 2153, sandbox=True
    )


def test_authorize_operation(tp_provider):
    payment = Payment()

    authorization = Authorization(
        status_code=-1,
        status_message="Solicitud de Autorizacion Registrada",
        form_url="https://forms.todopago.com.ar/formulario/commands?command=formulario&amp;m=a6104bad3-1be7-4e8e-932e-e927100b2e86&amp;fr=1",
        request_key="f5ad41bc-92ba-40ff-889d-8a23fe562a28",
        public_request_key="a6104bad3-1be7-4e8e-932e-e927100b2e86",
    )

    with patch(
        "python_todopago.TodoPagoConnector.authorize_operation",
        spec=True,
        return_value=authorization,
    ):
        _ = tp_provider.authorize_operation(payment)

    assert payment.status == PaymentStatus.WAITING
    assert payment.attrs.request_key == "f5ad41bc-92ba-40ff-889d-8a23fe562a28"


def test_approved_payment_notification(rf, tp_provider):
    payment = Payment()
    payment.attrs.request_key = "1fb7cc9a-14dd-42ec-bf1e-6d5820799642"
    payment.attrs.form_url = (
        "https://forms.todopago.com.ar/formulario/commands?command=formulario&amp;m=a6104bad3-1be7-4e8e-932e-e927100b2e86&amp;fr=1",
    )
    payment.save()

    request = rf.get(
        "/payments/process/d16695e8-b76d-4438-bd10-634545ecb1d6/",
        {"Answer": "44caba31-1373-4544-aa6b-42abff696944"},
    )

    operation_status = OperationStatus(
        status_code=-1,
        status_message="APROBADA",
        authorization_key="817824df-8614-4ce8-a6c9-abdf884024ab",
    )

    with patch(
        "python_todopago.TodoPagoConnector.get_operation_status",
        spec=True,
        return_value=operation_status,
    ), patch("payments.todopago.redirect", spec=True) as redirect:
        rv = tp_provider.process_callback(payment, request)

    assert rv == redirect(payment.get_success_url())
