from __future__ import annotations

import json
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded

from . import StripeProviderV3

# Secret key from https://stripe.com/docs/api/authentication
API_KEY = "sk_test_4eC39HqLyjWDarjtT1zdp7dc"
API_KEY_BAD = "aaaaaaa123"


class payment_attrs:
    session = dict


class Payment(Mock):
    id = 1
    description = "payment"
    currency = "USD"
    delivery = 0
    status = PaymentStatus.WAITING
    message = None
    tax = 0
    total = 100
    captured_amount = 0
    transaction_id = None
    billing_email = "john@doe.com"
    attrs = payment_attrs()

    def change_status(self, status, message=""):
        self.status = status
        self.message = message

    def get_failure_url(self):
        return "http://cancel.com"

    def get_process_url(self):
        return "http://example.com"

    def get_purchased_items(self):
        return []

    def get_success_url(self):
        return "http://success.com"


def test_provider_create_session_success():
    payment = Payment()
    provider = StripeProviderV3(api_key=API_KEY)
    return_value = {
        "id": "cs_test_...",
        "url": "https://checkout.stripe.com/c/pay/cs_test_...",
        "status": "open",
        "payment_status": "unpaid",
        "payment_intent": "pi_...",
    }
    with (
        patch("stripe.checkout.Session.create", return_value=return_value),
        pytest.raises(RedirectNeeded),
    ):
        provider.get_form(payment)

    assert "url" in payment.attrs.session
    assert "id" in payment.attrs.session
    assert payment.status == PaymentStatus.WAITING


def test_provider_create_session_failure():
    payment = Payment()
    provider = StripeProviderV3(api_key=API_KEY)

    with patch("stripe.checkout.Session.create") as f_session:
        f_session.side_effect = PaymentError("Error")
        with pytest.raises(PaymentError):
            provider.get_form(payment)

    assert payment.status == PaymentStatus.ERROR


def test_provider_create_session_failure_no_url():
    payment = Payment()
    provider = StripeProviderV3(api_key=API_KEY)
    return_value = {
        "status": "open",
        "payment_status": "unpaid",
        "payment_intent": "pi_...",
    }
    with (
        patch("stripe.checkout.Session.create", return_value=return_value),
        pytest.raises(PaymentError),
    ):
        provider.get_form(payment)

    assert "url" not in payment.attrs.session
    assert "id" not in payment.attrs.session


def test_provider_create_session_failure_with_transaction_id():
    payment = Payment()
    payment.transaction_id = "transaction-id"
    provider = StripeProviderV3(api_key=API_KEY)
    with patch("stripe.checkout.Session.create"), pytest.raises(PaymentError):
        provider.create_session(payment)


@pytest.mark.skip(reason="https://github.com/jazzband/django-payments/issues/444")
def test_provider_create_session_success_with_billing_name():
    payment = Payment()
    payment.billing_name = "Billy Ngname"
    provider = StripeProviderV3(api_key=API_KEY)
    provider.create_session(payment)


def test_provider_status_confirmed():
    payment = Payment()
    payment.attrs = payment_attrs()
    payment.transaction_id = "cs_test_..."
    provider = StripeProviderV3(api_key=API_KEY)

    class MockSession:
        payment_status = "paid"

    with patch("stripe.checkout.Session.retrieve", return_value=MockSession()):
        provider.status(payment)

    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.captured_amount == payment.total


def test_provider_status_not_paid():
    payment = Payment()
    payment.transaction_id = "cs_test_..."
    provider = StripeProviderV3(api_key=API_KEY)

    class MockSession:
        payment_status = "unpaid"

    with patch("stripe.checkout.Session.retrieve", return_value=MockSession()):
        provider.status(payment)

    assert payment.status == PaymentStatus.WAITING
    assert payment.captured_amount == 0


def test_provider_refund_failure_bad_status():
    payment = Payment()
    provider = StripeProviderV3(api_key=API_KEY)
    with pytest.raises(PaymentError):
        provider.refund(payment)


def test_provider_refund_failure_no_payment_intent():
    payment = Payment()
    payment.status = PaymentStatus.CONFIRMED
    assert isinstance(payment.attrs.session, dict)
    del payment.attrs.session["payment_intent"]
    provider = StripeProviderV3(api_key=API_KEY)
    with pytest.raises(PaymentError):
        provider.refund(payment)


def test_provider_refund_failure_stripe_error():
    payment = Payment()
    payment.status = PaymentStatus.CONFIRMED
    provider = StripeProviderV3(api_key=API_KEY)
    with patch("stripe.Refund.create") as f_refund:
        f_refund.side_effect = PaymentError("Stripe error")
        with pytest.raises(PaymentError):
            provider.refund(payment)


## Provider.refund() should not change the payment status.
## Status management is handled by BasePayment.refund().
## Refunds should be performed via payment.refund() (see docs/refund.rst).
def test_provider_refund_success():
    payment = Payment()
    payment.status = PaymentStatus.CONFIRMED
    payment.attrs.session["payment_intent"] = "pi_..."
    provider = StripeProviderV3(api_key=API_KEY)
    return_value = {
        "id": "re_...",
        "payment_status": "succeeded",
        "amount": 100,
    }

    with patch("stripe.Refund.create", return_value=return_value):
        provider.refund(payment)

    assert payment.status == PaymentStatus.CONFIRMED


def test_provider_refund_returns_currency_units():
    payment = Payment()
    payment.status = PaymentStatus.CONFIRMED
    payment.total = 30
    payment.currency = "USD"
    payment.attrs.session["payment_intent"] = "pi_..."
    provider = StripeProviderV3(api_key=API_KEY)
    return_value = {
        "id": "re_...",
        "payment_status": "succeeded",
        "amount": 3000,
    }

    with patch("stripe.Refund.create", return_value=return_value) as mock_create:
        result = provider.refund(payment)
        mock_create.assert_called_once_with(
            payment_intent="pi_...",
            amount=3000,
            reason="requested_by_customer",
        )

    assert result == 30


def test_provider_refund_partial_returns_currency_units():
    payment = Payment()
    payment.status = PaymentStatus.CONFIRMED
    payment.total = 30
    payment.currency = "USD"
    payment.attrs.session["payment_intent"] = "pi_..."
    provider = StripeProviderV3(api_key=API_KEY)
    return_value = {
        "id": "re_...",
        "payment_status": "succeeded",
        "amount": 1500,
    }

    with patch("stripe.Refund.create", return_value=return_value) as mock_create:
        result = provider.refund(payment, amount=15)
        mock_create.assert_called_once_with(
            payment_intent="pi_...",
            amount=1500,
            reason="requested_by_customer",
        )

    assert result == 15


def test_provider_refund_zero_decimal_currency_returns_currency_units():
    payment = Payment()
    payment.status = PaymentStatus.CONFIRMED
    payment.total = 3000
    payment.currency = "JPY"
    payment.attrs.session["payment_intent"] = "pi_..."
    provider = StripeProviderV3(api_key=API_KEY)
    return_value = {
        "id": "re_...",
        "payment_status": "succeeded",
        "amount": 3000,
    }

    with patch("stripe.Refund.create", return_value=return_value) as mock_create:
        result = provider.refund(payment, amount=3000)
        mock_create.assert_called_once_with(
            payment_intent="pi_...",
            amount=3000,
            reason="requested_by_customer",
        )

    assert result == 3000


def _make_webhook_request(event_type, session_status, payment_status):
    body = json.dumps(
        {
            "type": event_type,
            "data": {
                "object": {
                    "status": session_status,
                    "payment_status": payment_status,
                    "payment_intent": "pi_...",
                }
            },
        }
    )
    request = Mock()
    request.body = body
    return request


def test_process_data_sets_captured_amount_on_payment():
    payment = Payment()
    provider = StripeProviderV3(api_key=API_KEY, secure_endpoint=False)
    request = _make_webhook_request(
        event_type="checkout.session.completed",
        session_status="complete",
        payment_status="paid",
    )

    provider.process_data(payment, request)

    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.captured_amount == payment.total


def test_process_data_does_not_set_captured_amount_on_expiry():
    payment = Payment()
    provider = StripeProviderV3(api_key=API_KEY, secure_endpoint=False)
    request = _make_webhook_request(
        event_type="checkout.session.expired",
        session_status="expired",
        payment_status="unpaid",
    )

    provider.process_data(payment, request)

    assert payment.status == PaymentStatus.REJECTED
    assert payment.captured_amount == 0
