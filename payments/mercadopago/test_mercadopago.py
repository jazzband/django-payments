from typing import Optional
from unittest.mock import Mock
from unittest.mock import call
from unittest.mock import patch

import pytest

from payments import PaymentError
from payments import PaymentStatus
from payments import PurchasedItem
from payments import RedirectNeeded
from payments.mercadopago import MercadoPagoProvider


class Payment(Mock):
    id = 1
    description = "payment"
    currency = "ARS"
    delivery = 10
    status = PaymentStatus.WAITING
    message = None
    tax = 10
    total = 100
    captured_amount = 0
    transaction_id: Optional[str] = None
    billing_email = "john@doe.com"

    def change_status(self, status, message=""):
        self.status = status
        self.message = message

    def change_fraud_status(self, status, message="", commit=True):
        self.fraud_status = status
        self.fraud_message = message

    def capture(self, amount=None):
        amount = amount or self.total
        self.captured_amount = amount
        self.change_status(PaymentStatus.CONFIRMED)

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
            price="1999",
            currency="ARS",
        )


@pytest.fixture
def mp_provider():
    return MercadoPagoProvider("fake_access_token", True)


# These are mock request and responses are based on valid data that actually worked in
# the live environment. Values have been replaced with random numbers / names /
# etc. However, the structure of the payloads matches what the API currently uses.


def test_approved_payment_notification(rf, mp_provider: MercadoPagoProvider):
    payment = Payment()

    request = rf.get(
        "/payments/process/d16695e8-b76d-4438-bd10-634545ecb1d6/",
        {
            "collection_id": "14543542354",
            "collection_status": "approved",
            "external_reference": "e312623454323b6a8605de11873cbb82",
            "merchant_account_id": "null",
            "merchant_order_id": "2344532517",
            "payment_id": "14345344918",
            "payment_type": "credit_card",
            "preference_id": "151235340-fc9fcecd-6e38-4e50-adac-a10abab4f138",
            "processing_mode": "aggregator",
            "site_id": "MLA",
            "status": "approved",
        },
    )

    payment_info_response = {
        "response": {
            "acquirer_reconciliation": [],
            "additional_info": {
                "available_balance": None,
                "ip_address": "127.19.22.46",
                "items": [
                    {
                        "category_id": None,
                        "description": "454716",
                        "id": None,
                        "picture_url": None,
                        "quantity": "1",
                        "title": "Order #454416",
                        "unit_price": "655.0",
                    }
                ],
                "nsu_processadora": None,
            },
            "authorization_code": "345385",
            "binary_mode": False,
            "brand_id": None,
            "call_for_authorize_id": None,
            "captured": True,
            "card": {
                "cardholder": {
                    "identification": {"number": "45354441", "type": "DNI"},
                    "name": "María Perez",
                },
                "date_created": "2020-10-10T17:27:45.000-04:00",
                "date_last_updated": "2021-04-21T13:37:38.000-04:00",
                "expiration_month": 3,
                "expiration_year": 2023,
                "first_six_digits": "235237",
                "id": "8945698155",
                "last_four_digits": "5847",
            },
            "charges_details": [],
            "collector_id": 153453450,
            "corporation_id": None,
            "counter_currency": None,
            "coupon_amount": 0,
            "currency_id": "ARS",
            "date_approved": "2021-04-21T13:44:17.000-04:00",
            "date_created": "2021-04-21T13:44:15.000-04:00",
            "date_last_updated": "2021-04-21T13:44:17.000-04:00",
            "date_of_expiration": None,
            "deduction_schema": None,
            "description": "Order #343716",
            "differential_pricing_id": None,
            "external_reference": "e2353245324a4b6a8605d565573cbb82",
            "fee_details": [
                {"amount": 47.49, "fee_payer": "collector", "type": "mercadopago_fee"}
            ],
            "id": 34534444918,
            "installments": 1,
            "integrator_id": None,
            "issuer_id": "688",
            "live_mode": True,
            "marketplace_owner": None,
            "merchant_account_id": None,
            "merchant_number": None,
            "metadata": {},
            "money_release_date": "2021-04-21T13:44:17.000-04:00",
            "money_release_schema": None,
            "notification_url": "https://www.example.com/payments/process/d14343e8-b76d-4438-bd10-633453ecb1d6/",
            "operation_type": "regular_payment",
            "order": {"id": "3453449517", "type": "mercadopago"},
            "payer": {
                "email": "mariaperez@example.com",
                "entity_type": None,
                "first_name": "maria",
                "id": "53474545",
                "identification": {"number": "23423341", "type": "DNI"},
                "last_name": "perez",
                "operator_id": None,
                "phone": {"area_code": "011", "extension": None, "number": "40004444"},
                "type": "registered",
            },
            "payment_method_id": "cabal",
            "payment_type_id": "credit_card",
            "platform_id": None,
            "point_of_interaction": {},
            "pos_id": None,
            "processing_mode": "aggregator",
            "refunds": [],
            "shipping_amount": 0,
            "sponsor_id": None,
            "statement_descriptor": "MERCADOPAGO - TEST",
            "status": "approved",
            "status_detail": "accredited",
            "store_id": None,
            "taxes_amount": 0,
            "transaction_amount": 655,
            "transaction_amount_refunded": 0,
            "transaction_details": {
                "acquirer_reference": None,
                "external_resource_url": None,
                "financial_institution": None,
                "installment_amount": 655,
                "net_received_amount": 606.2,
                "overpaid_amount": 0,
                "payable_deferral_period": None,
                "payment_method_reference_id": "423423523525349",
                "total_paid_amount": 655,
            },
        },
        "status": 200,
    }

    with patch(
        "mercadopago.resources.payment.Payment.get",
        spec=True,
        return_value=payment_info_response,
    ) as payment_info, patch(
        "payments.mercadopago.redirect",
        spec=True,
    ) as redirect:
        rv = mp_provider.process_data(payment, request)

    assert payment_info.call_count == 1
    assert rv == redirect(payment.get_success_url())


def test_create_preference_that_already_exists(mp_provider: MercadoPagoProvider):
    payment = Payment()
    payment.transaction_id = "123"

    with pytest.raises(ValueError, match="payment already has a preference"):
        mp_provider.create_preference(payment)


def test_create_preference_failure(mp_provider: MercadoPagoProvider):
    preference_info = {
        "status": 500,
        "response": "internal server error",
    }

    payment = Payment()

    with patch(
        "mercadopago.resources.preference.Preference.create",
        spec=True,
        return_value=preference_info,
    ), pytest.raises(
        PaymentError,
        match="Failed to create MercadoPago preference.",
    ):
        mp_provider.create_preference(payment)


def test_process_successful_collection(mp_provider: MercadoPagoProvider):
    payment_info = {
        "status": 200,
        "response": {"status": "approved"},
    }

    payment = Payment()
    with patch(
        "mercadopago.resources.payment.Payment.get",
        spec=True,
        return_value=payment_info,
    ):
        mp_provider.process_collection(payment, "12")

    assert payment.status == PaymentStatus.CONFIRMED


def test_process_failed_collection(mp_provider: MercadoPagoProvider):
    payment_info = {
        "status": 404,
    }

    payment = Payment()
    with patch(
        "mercadopago.resources.payment.Payment.get",
        spec=True,
        return_value=payment_info,
    ), pytest.raises(
        PaymentError,
        match="MercadoPago sent invalid payment data.",
    ):
        mp_provider.process_collection(payment, "12")

    assert payment.status == PaymentStatus.ERROR


def test_process_pending_collection(mp_provider: MercadoPagoProvider):
    payment_info = {
        "status": 200,
        "response": {"status": "pending"},
    }

    payment = Payment()
    with patch(
        "mercadopago.resources.payment.Payment.get",
        spec=True,
        return_value=payment_info,
    ):
        mp_provider.process_collection(payment, "12")

    assert payment.status == PaymentStatus.WAITING


def test_get_preference(mp_provider: MercadoPagoProvider):
    preference = Mock()
    mocked_response = {
        "status": 200,
        "response": preference,
    }

    payment = Payment()
    payment.transaction_id = "ABJ122"
    with patch(
        "mercadopago.resources.preference.Preference.get",
        spec=True,
        return_value=mocked_response,
    ) as get_preference:
        assert mp_provider.get_preference(payment) == preference

    assert get_preference.call_count == 1
    assert get_preference.call_args == call(payment.transaction_id)


def test_get_preference_with_missing_transaction_id(mp_provider: MercadoPagoProvider):
    payment = Payment()

    with pytest.raises(ValueError, match="payment does not have a preference"):
        mp_provider.get_preference(payment)


def test_get_preference_internal_error(mp_provider: MercadoPagoProvider):
    mocked_response = {
        "status": 500,
        "response": "Internal error",
    }

    payment = Payment()
    payment.transaction_id = "ABJ122"
    with patch(
        "mercadopago.resources.preference.Preference.get",
        spec=True,
        return_value=mocked_response,
    ) as get_preference:
        with pytest.raises(
            PaymentError, match="Failed to retrieve MercadoPago preference."
        ):
            mp_provider.get_preference(payment)

    assert get_preference.call_count == 1
    assert get_preference.call_args == call(payment.transaction_id)


def test_get_form_for_existing_preference(mp_provider: MercadoPagoProvider):
    mocked_response = {
        "status": 200,
        "response": {"sandbox_init_point": "https://example.com/pay"},
    }

    payment = Payment()
    payment.transaction_id = "ABJ122"
    with patch(
        "mercadopago.resources.preference.Preference.get",
        spec=True,
        return_value=mocked_response,
    ) as get_preference:
        with pytest.raises(RedirectNeeded) as exc_info:
            mp_provider.get_form(payment)

    assert get_preference.call_count == 1
    assert get_preference.call_args == call(payment.transaction_id)
    assert str(exc_info.value) == "https://example.com/pay"


def test_get_form_for_inexistent_preference(mp_provider: MercadoPagoProvider):
    mocked_response = {
        "status": 200,
        "response": {
            "id": "AZ12",
            "sandbox_init_point": "https://example.com/pay",
        },
    }

    payment = Payment()
    with patch(
        "mercadopago.resources.preference.Preference.create",
        spec=True,
        return_value=mocked_response,
    ) as get_preference:
        with pytest.raises(RedirectNeeded) as exc_info:
            mp_provider.get_form(payment)

    assert get_preference.call_count == 1
    assert str(exc_info.value) == "https://example.com/pay"
