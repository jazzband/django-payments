"""Tests for Stripe transaction fee retrieval."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from payments import PaymentStatus
from payments.stripe import StripeProviderV3

API_KEY = "sk_test_123"


class Payment:
    """Mock payment object for testing."""

    def __init__(self):
        object.__setattr__(self, "_attrs", {})
        self.id = 1
        self.token = "test-token"
        self.status = PaymentStatus.WAITING
        self.total = Decimal("100.00")
        self.currency = "USD"
        self.extra_data = "{}"

    @property
    def attrs(self):
        return self

    def __setattr__(self, key, value):
        if key.startswith("_"):
            object.__setattr__(self, key, value)
        else:
            self._attrs[key] = value

    def __getattr__(self, key):
        if key == "_attrs":
            return object.__getattribute__(self, key)
        return self._attrs.get(key)

    def change_status(self, status):
        self.status = status

    def save(self):
        pass


@pytest.mark.django_db
@patch("stripe.BalanceTransaction.retrieve")
@patch("stripe.PaymentIntent.retrieve")
def test_retrieve_transaction_fee_success(mock_pi_retrieve, mock_bt_retrieve):
    """Test successful fee retrieval from Stripe API."""
    provider = StripeProviderV3(api_key=API_KEY)

    # Mock Stripe API responses
    mock_pi_retrieve.return_value = {
        "id": "pi_test_123",
        "charges": {
            "data": [
                {
                    "id": "ch_test_123",
                    "balance_transaction": "txn_test_123",
                }
            ]
        },
    }

    mock_bt_retrieve.return_value = {
        "id": "txn_test_123",
        "fee": 320,  # $3.20 in cents
        "net": 9680,
        "currency": "usd",
    }

    # Call the fee retrieval method
    fee = provider._retrieve_transaction_fee("pi_test_123")

    # Verify the fee was retrieved correctly
    assert fee == 320
    mock_pi_retrieve.assert_called_once_with("pi_test_123")
    mock_bt_retrieve.assert_called_once_with("txn_test_123")


@pytest.mark.django_db
@patch("stripe.PaymentIntent.retrieve")
def test_retrieve_transaction_fee_no_charges(mock_pi_retrieve):
    """Test fee retrieval when PaymentIntent has no charges."""
    provider = StripeProviderV3(api_key=API_KEY)

    # Mock PaymentIntent with no charges
    mock_pi_retrieve.return_value = {
        "id": "pi_test_123",
        "charges": {"data": []},
    }

    fee = provider._retrieve_transaction_fee("pi_test_123")

    # Should return None when no charges found
    assert fee is None


@pytest.mark.django_db
@patch("stripe.PaymentIntent.retrieve")
def test_retrieve_transaction_fee_no_balance_transaction(mock_pi_retrieve):
    """Test fee retrieval when charge has no balance_transaction."""
    provider = StripeProviderV3(api_key=API_KEY)

    # Mock charge without balance_transaction
    mock_pi_retrieve.return_value = {
        "id": "pi_test_123",
        "charges": {
            "data": [
                {
                    "id": "ch_test_123",
                    # No balance_transaction field
                }
            ]
        },
    }

    fee = provider._retrieve_transaction_fee("pi_test_123")

    # Should return None when no balance_transaction found
    assert fee is None


@pytest.mark.django_db
@patch("stripe.PaymentIntent.retrieve")
def test_retrieve_transaction_fee_stripe_error(mock_pi_retrieve):
    """Test fee retrieval when Stripe API raises an error."""
    import stripe

    provider = StripeProviderV3(api_key=API_KEY)

    # Mock Stripe API error
    mock_pi_retrieve.side_effect = stripe.error.StripeError("API Error")

    fee = provider._retrieve_transaction_fee("pi_test_123")

    # Should return None on error (logged but not raised)
    assert fee is None


@pytest.mark.django_db
@patch("stripe.BalanceTransaction.retrieve")
@patch("stripe.PaymentIntent.retrieve")
def test_process_data_stores_fee_in_session_completed(
    mock_pi_retrieve, mock_bt_retrieve
):
    """Test that process_data stores the transaction fee for checkout.session.completed."""
    payment = Payment()
    provider = StripeProviderV3(api_key=API_KEY, endpoint_secret="whsec_test")

    # Mock Stripe API responses for fee retrieval
    mock_pi_retrieve.return_value = {
        "id": "pi_test_123",
        "charges": {
            "data": [
                {
                    "id": "ch_test_123",
                    "balance_transaction": "txn_test_123",
                }
            ]
        },
    }

    mock_bt_retrieve.return_value = {
        "id": "txn_test_123",
        "fee": 450,  # $4.50 in cents
        "net": 9550,
        "currency": "usd",
    }

    # Create webhook event
    event_data = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "payment_intent": "pi_test_123",
                "payment_status": "paid",
                "status": "complete",
            }
        },
    }

    request = Mock()
    request.body = ""
    request.headers = {}

    # Mock the event payload return
    with patch.object(provider, "return_event_payload", return_value=event_data):
        provider.process_data(payment, request)

    # Verify payment status changed
    assert payment.status == PaymentStatus.CONFIRMED

    # Verify fee was stored
    assert payment.stripe_fee == 450


@pytest.mark.django_db
def test_process_data_handles_missing_payment_intent():
    """Test that process_data handles sessions without payment_intent gracefully."""
    payment = Payment()
    provider = StripeProviderV3(api_key=API_KEY, endpoint_secret="whsec_test")

    # Create webhook event without payment_intent (e.g., setup mode)
    event_data = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                # No payment_intent field
                "payment_status": "paid",
                "status": "complete",
            }
        },
    }

    request = Mock()
    request.body = ""
    request.headers = {}

    # Mock the event payload return
    with patch.object(provider, "return_event_payload", return_value=event_data):
        provider.process_data(payment, request)

    # Should still confirm payment even without fee
    assert payment.status == PaymentStatus.CONFIRMED

    # Fee should not be set
    assert not hasattr(payment, "stripe_fee") or payment.stripe_fee is None


@pytest.mark.django_db
@patch("stripe.BalanceTransaction.retrieve")
@patch("stripe.PaymentIntent.retrieve")
def test_process_data_fee_retrieval_error_does_not_fail_webhook(
    mock_pi_retrieve, mock_bt_retrieve
):
    """Test that fee retrieval errors don't fail the webhook processing."""
    payment = Payment()
    provider = StripeProviderV3(api_key=API_KEY, endpoint_secret="whsec_test")

    # Mock Stripe API to raise an error
    mock_pi_retrieve.side_effect = Exception("API Error")

    # Create webhook event
    event_data = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "payment_intent": "pi_test_123",
                "payment_status": "paid",
                "status": "complete",
            }
        },
    }

    request = Mock()
    request.body = ""
    request.headers = {}

    # Mock the event payload return
    with patch.object(provider, "return_event_payload", return_value=event_data):
        response = provider.process_data(payment, request)

    # Webhook should succeed despite fee retrieval failure
    assert response.status_code == 200
    assert payment.status == PaymentStatus.CONFIRMED

    # Fee should not be set
    assert not hasattr(payment, "stripe_fee") or payment.stripe_fee is None
