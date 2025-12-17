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


@pytest.mark.skip(reason="Breaks global state and asserts nothing")
def test_provider_status():
    payment = Payment()
    provider = StripeProviderV3(api_key=API_KEY)

    class return_value:
        payment_status = "paid"

    with patch("stripe.checkout.Session.retrieve", return_value=return_value):
        provider.status(payment)


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

    assert payment.status == PaymentStatus.REFUNDED


def test_get_line_items_includes_description():
    """Payment description should be included in product line items."""
    payment = Payment()
    payment.description = "Premium subscription for user@example.com"
    payment.token = "test-token-123"
    provider = StripeProviderV3(api_key=API_KEY)
    
    line_items = provider.get_line_items(payment)

    assert len(line_items) == 1
    product_data = line_items[0]["price_data"]["product_data"]
    assert product_data["name"] == "Order #test-token-123"
    assert product_data["description"] == "Premium subscription for user@example.com"


def test_get_line_items_without_description():
    """Line items should work without description (backward compatibility)."""
    payment = Payment()
    payment.description = ""  # Empty description
    payment.token = "test-token-456"
    provider = StripeProviderV3(api_key=API_KEY)
    
    line_items = provider.get_line_items(payment)

    assert len(line_items) == 1
    product_data = line_items[0]["price_data"]["product_data"]
    assert product_data["name"] == "Order #test-token-456"
    # Description should be None when empty (dataclass default)
    assert product_data["description"] is None


def test_create_session_includes_billing_metadata():
    """Billing address and name should be included in session metadata."""
    payment = Payment()
    payment.billing_first_name = "John"
    payment.billing_last_name = "Doe"
    payment.billing_address_1 = "123 Main St"
    payment.billing_address_2 = "Apt 4B"
    payment.billing_city = "New York"
    payment.billing_postcode = "10001"
    payment.billing_country_code = "US"
    payment.billing_country_area = "NY"
    payment.billing_phone = "+1234567890"
    
    provider = StripeProviderV3(api_key=API_KEY)
    
    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.return_value = {
            "id": "cs_test_123",
            "url": "https://checkout.stripe.com/test",
        }
        provider.create_session(payment)
    
    # Verify metadata was passed
    call_kwargs = mock_create.call_args[1]
    metadata = call_kwargs["metadata"]
    
    assert metadata["customer_name"] == "John Doe"
    assert metadata["billing_address_1"] == "123 Main St"
    assert metadata["billing_address_2"] == "Apt 4B"
    assert metadata["billing_city"] == "New York"
    assert metadata["billing_postcode"] == "10001"
    assert metadata["billing_country_code"] == "US"
    assert metadata["billing_country_area"] == "NY"
    assert metadata["billing_phone"] == "+1234567890"


def test_create_session_billing_metadata_partial():
    """Session should include only provided billing fields in metadata."""
    payment = Payment()
    payment.billing_first_name = "Jane"
    payment.billing_last_name = ""  # Explicitly empty
    payment.billing_city = "Boston"
    payment.billing_address_1 = ""
    payment.billing_address_2 = ""
    payment.billing_postcode = ""
    payment.billing_country_code = ""
    payment.billing_country_area = ""
    payment.billing_phone = ""
    
    provider = StripeProviderV3(api_key=API_KEY)
    
    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.return_value = {
            "id": "cs_test_456",
            "url": "https://checkout.stripe.com/test",
        }
        provider.create_session(payment)
    
    call_kwargs = mock_create.call_args[1]
    metadata = call_kwargs["metadata"]
    
    # Only provided fields should be present
    assert metadata["customer_name"] == "Jane"
    assert metadata["billing_city"] == "Boston"
    assert "billing_address_1" not in metadata
    assert "billing_postcode" not in metadata


def test_create_session_no_billing_metadata():
    """Session should work without billing data (backward compatibility)."""
    payment = Payment()
    # Explicitly set all billing fields to empty
    payment.billing_first_name = ""
    payment.billing_last_name = ""
    payment.billing_address_1 = ""
    payment.billing_address_2 = ""
    payment.billing_city = ""
    payment.billing_postcode = ""
    payment.billing_country_code = ""
    payment.billing_country_area = ""
    payment.billing_phone = ""
    
    provider = StripeProviderV3(api_key=API_KEY)
    
    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.return_value = {
            "id": "cs_test_789",
            "url": "https://checkout.stripe.com/test",
        }
        provider.create_session(payment)
    
    call_kwargs = mock_create.call_args[1]
    
    # payment_token is always added to metadata (for webhook token extraction)
    assert "metadata" in call_kwargs
    assert call_kwargs["metadata"]["payment_token"] == str(payment.token)
    # No other billing data should be present
    assert len(call_kwargs["metadata"]) == 1


def test_create_session_billing_address_uses_stripe_default():
    """Billing address collection should use Stripe's default 'auto' behavior.

    We don't set billing_address_collection, letting Stripe decide when to collect
    address (e.g., for tax compliance). The address data is stored in metadata
    for audit trail regardless.
    """
    payment = Payment()
    payment.billing_address_1 = "456 Oak Ave"
    payment.billing_city = "Chicago"
    payment.billing_postcode = "60601"
    payment.billing_country_code = "US"
    
    provider = StripeProviderV3(api_key=API_KEY)
    
    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.return_value = {
            "id": "cs_test_address",
            "url": "https://checkout.stripe.com/test",
        }
        provider.create_session(payment)
    
    call_kwargs = mock_create.call_args[1]
    
    # billing_address_collection should NOT be set - use Stripe's default "auto"
    assert "billing_address_collection" not in call_kwargs
    
    # But metadata should contain the address for audit trail
    assert "metadata" in call_kwargs
    assert call_kwargs["metadata"]["billing_address_1"] == "456 Oak Ave"
    assert call_kwargs["metadata"]["billing_city"] == "Chicago"


@pytest.mark.skip(reason="customer_details functionality was removed")
def test_create_session_billing_metadata_only_with_name():
    """Metadata should store name even when address fields are empty."""
    payment = Payment()
    payment.billing_first_name = "Alice"
    payment.billing_last_name = "Smith"
    # Explicitly set address fields to empty
    payment.billing_address_1 = ""
    payment.billing_address_2 = ""
    payment.billing_city = ""
    payment.billing_postcode = ""
    payment.billing_country_code = ""
    payment.billing_country_area = ""
    payment.billing_phone = ""
    
    provider = StripeProviderV3(api_key=API_KEY)
    
    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.return_value = {
            "id": "cs_test_no_address",
            "url": "https://checkout.stripe.com/test",
        }
        provider.create_session(payment)
    
    call_kwargs = mock_create.call_args[1]
    
    # billing_address_collection should not be set (use Stripe default)
    assert "billing_address_collection" not in call_kwargs
    
    # Metadata should contain name but not empty address fields
    assert "metadata" in call_kwargs
    assert call_kwargs["metadata"]["customer_name"] == "Alice Smith"
    assert "billing_address_1" not in call_kwargs["metadata"]
    """Checkout form should be pre-filled with billing address when available."""
    payment = Payment()
    payment.billing_address_1 = "789 Pine St"
    payment.billing_address_2 = "Apt 3B"
    payment.billing_city = "Seattle"
    payment.billing_postcode = "98101"
    payment.billing_country_area = "WA"
    payment.billing_country_code = "US"

    provider = StripeProviderV3(api_key=API_KEY)

    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.return_value = {
            "id": "cs_test_prefill",
            "url": "https://checkout.stripe.com/test",
        }
        provider.create_session(payment)

    call_kwargs = mock_create.call_args[1]

    # customer_details should contain the address for pre-fill
    assert "customer_details" in call_kwargs
    address = call_kwargs["customer_details"]["address"]
    assert address["line1"] == "789 Pine St"
    assert address["line2"] == "Apt 3B"
    assert address["city"] == "Seattle"
    assert address["postal_code"] == "98101"
    assert address["state"] == "WA"
    assert address["country"] == "US"


@pytest.mark.skip(reason="customer_details functionality was removed")
def test_create_session_prefills_partial_address():
    """Checkout form pre-fill should only include provided address fields."""
    payment = Payment()
    payment.billing_address_1 = "123 Main St"
    payment.billing_country_code = "US"
    # Explicitly set other fields to empty (simulating partial form data)
    payment.billing_address_2 = ""
    payment.billing_city = ""
    payment.billing_postcode = ""
    payment.billing_country_area = ""

    provider = StripeProviderV3(api_key=API_KEY)

    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.return_value = {
            "id": "cs_test_partial_prefill",
            "url": "https://checkout.stripe.com/test",
        }
        provider.create_session(payment)

    call_kwargs = mock_create.call_args[1]

    # customer_details should contain only the provided fields
    assert "customer_details" in call_kwargs
    address = call_kwargs["customer_details"]["address"]
    assert address["line1"] == "123 Main St"
    assert address["country"] == "US"
    # Empty fields should not be included
    assert "line2" not in address
    assert "city" not in address
    assert "postal_code" not in address
    assert "state" not in address


def test_create_session_no_prefill_with_existing_customer():
    """Pre-fill should not be used when reusing existing Stripe Customer."""
    payment = Payment()
    payment.billing_address_1 = "456 Oak Ave"
    payment.billing_city = "Portland"
    payment.billing_country_code = "US"

    # Mock that payment has renew data with existing customer
    payment.get_renew_data = lambda: {"customer_id": "cus_existing123"}

    provider = StripeProviderV3(api_key=API_KEY, store_payment_method=True)

    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.return_value = {
            "id": "cs_test_no_prefill",
            "url": "https://checkout.stripe.com/test",
        }
        provider.create_session(payment)

    call_kwargs = mock_create.call_args[1]

    # Should use existing customer
    assert call_kwargs["customer"] == "cus_existing123"

    # Should NOT have customer_details (customer already has address)
    assert "customer_details" not in call_kwargs


class MockRequest:
    """Mock Django request object for webhook tests."""

    def __init__(self, body, headers=None):
        self.body = body
        self.headers = headers or {}


def test_get_token_from_request_checkout_session_completed():
    """Test extracting payment token from checkout.session.completed event."""
    provider = StripeProviderV3(api_key=API_KEY, endpoint_secret="whsec_test")
    
    event_data = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "client_reference_id": "payment-token-123",
                "status": "complete",
            }
        },
    }
    request = MockRequest(
        body=json.dumps(event_data).encode(),
        headers={"STRIPE_SIGNATURE": "test_sig"},
    )
    
    with patch("stripe.Webhook.construct_event", return_value=event_data):
        token = provider.get_token_from_request(payment=None, request=request)
        assert token == "payment-token-123"


def test_get_token_from_request_setup_intent_succeeded_with_metadata():
    """Test extracting payment token from setup_intent.succeeded with metadata."""
    provider = StripeProviderV3(api_key=API_KEY, endpoint_secret="whsec_test")
    
    event_data = {
        "type": "setup_intent.succeeded",
        "data": {
            "object": {
                "id": "seti_test_123",
                "customer": "cus_test_123",
                "created": 1234567890,
                "metadata": {
                    "payment_token": "payment-token-456",
                    "payment_id": "123",
                },
            }
        },
    }
    request = MockRequest(
        body=json.dumps(event_data).encode(),
        headers={"STRIPE_SIGNATURE": "test_sig"},
    )
    
    with patch("stripe.Webhook.construct_event", return_value=event_data):
        token = provider.get_token_from_request(payment=None, request=request)
        assert token == "payment-token-456"


def test_get_token_from_request_setup_intent_succeeded_fallback_to_session():
    """Test extracting payment token from setup_intent.succeeded via session lookup."""
    provider = StripeProviderV3(api_key=API_KEY, endpoint_secret="whsec_test")
    
    event_data = {
        "type": "setup_intent.succeeded",
        "data": {
            "object": {
                "id": "seti_test_123",
                "customer": "cus_test_123",
                "created": 1234567890,
                "metadata": {},  # No payment_token in metadata
            }
        },
    }
    
    # Mock session lookup
    mock_session = {
        "id": "cs_test_123",
        "mode": "setup",
        "customer": "cus_test_123",
        "created": 1234567890,
        "client_reference_id": "payment-token-789",
        "metadata": {},
    }
    
    request = MockRequest(
        body=json.dumps(event_data).encode(),
        headers={"STRIPE_SIGNATURE": "test_sig"},
    )
    
    with (
        patch("stripe.Webhook.construct_event", return_value=event_data),
        patch(
            "stripe.checkout.Session.list",
            return_value=Mock(data=[mock_session]),
        ),
    ):
        token = provider.get_token_from_request(payment=None, request=request)
        assert token == "payment-token-789"


def test_get_token_from_request_setup_intent_succeeded_fallback_to_session_metadata():
    """Test extracting payment token from session metadata when client_reference_id missing."""
    provider = StripeProviderV3(api_key=API_KEY, endpoint_secret="whsec_test")
    
    event_data = {
        "type": "setup_intent.succeeded",
        "data": {
            "object": {
                "id": "seti_test_123",
                "customer": "cus_test_123",
                "created": 1234567890,
                "metadata": {},
            }
        },
    }
    
    mock_session = {
        "id": "cs_test_123",
        "mode": "setup",
        "customer": "cus_test_123",
        "created": 1234567890,
        "client_reference_id": None,
        "metadata": {"payment_token": "payment-token-from-metadata"},
    }
    
    request = MockRequest(
        body=json.dumps(event_data).encode(),
        headers={"STRIPE_SIGNATURE": "test_sig"},
    )
    
    with (
        patch("stripe.Webhook.construct_event", return_value=event_data),
        patch(
            "stripe.checkout.Session.list",
            return_value=Mock(data=[mock_session]),
        ),
    ):
        token = provider.get_token_from_request(payment=None, request=request)
        assert token == "payment-token-from-metadata"


def test_get_token_from_request_checkout_session_expired():
    """Test that checkout.session.expired events can extract token from metadata."""
    provider = StripeProviderV3(api_key=API_KEY, endpoint_secret="whsec_test")
    
    event_data = {
        "type": "checkout.session.expired",
        "data": {
            "object": {
                "id": "cs_test_123",
                "status": "expired",
                # Expired sessions might not have client_reference_id
                "metadata": {"payment_token": "payment-token-expired"},
            }
        },
    }
    request = MockRequest(
        body=json.dumps(event_data).encode(),
        headers={"STRIPE_SIGNATURE": "test_sig"},
    )
    
    with patch("stripe.Webhook.construct_event", return_value=event_data):
        token = provider.get_token_from_request(payment=None, request=request)
        assert token == "payment-token-expired"


@pytest.mark.django_db
def test_process_data_setup_intent_succeeded():
    """Test processing setup_intent.succeeded webhook event."""
    payment = Payment()
    payment.token = "payment-token-123"
    payment.set_renew_token = Mock()
    
    provider = StripeProviderV3(
        api_key=API_KEY,
        endpoint_secret="whsec_test",
        store_payment_method=True,
    )
    
    event_data = {
        "type": "setup_intent.succeeded",
        "data": {
            "object": {
                "id": "seti_test_123",
                "customer": "cus_test_123",
                "payment_method": "pm_test_123",
                "status": "succeeded",
            }
        },
    }
    
    mock_payment_method = Mock()
    mock_payment_method.type = "card"
    mock_payment_method.card = Mock()
    mock_payment_method.card.exp_year = 2025
    mock_payment_method.card.exp_month = 12
    mock_payment_method.card.last4 = "4242"
    
    request = MockRequest(
        body=json.dumps(event_data).encode(),
        headers={"STRIPE_SIGNATURE": "test_sig"},
    )
    
    with (
        patch("stripe.Webhook.construct_event", return_value=event_data),
        patch("stripe.PaymentMethod.retrieve", return_value=mock_payment_method),
    ):
        response = provider.process_data(payment, request)
        
        assert response.status_code == 200
        assert payment.status == PaymentStatus.CONFIRMED
        payment.set_renew_token.assert_called_once_with(
            token="pm_test_123",
            customer_id="cus_test_123",
            card_expire_year=2025,
            card_expire_month=12,
            card_masked_number="4242",
        )


@pytest.mark.django_db
def test_process_data_checkout_session_completed():
    """Test processing checkout.session.completed webhook event."""
    payment = Payment()
    payment.token = "payment-token-123"
    payment.set_renew_token = Mock()
    
    provider = StripeProviderV3(
        api_key=API_KEY,
        endpoint_secret="whsec_test",
        store_payment_method=True,
    )
    
    event_data = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "status": "complete",
                "payment_status": "paid",
                "payment_intent": "pi_test_123",
                "mode": "payment",
            }
        },
    }
    
    mock_payment_intent = Mock()
    mock_payment_intent.payment_method = "pm_test_123"
    mock_payment_intent.customer = "cus_test_123"
    
    mock_payment_method = Mock()
    mock_payment_method.type = "card"
    mock_payment_method.card = Mock()
    mock_payment_method.card.exp_year = 2025
    mock_payment_method.card.exp_month = 12
    mock_payment_method.card.last4 = "4242"
    
    request = MockRequest(
        body=json.dumps(event_data).encode(),
        headers={"STRIPE_SIGNATURE": "test_sig"},
    )
    
    with (
        patch("stripe.Webhook.construct_event", return_value=event_data),
        patch("stripe.PaymentIntent.retrieve", return_value=mock_payment_intent),
        patch("stripe.PaymentMethod.retrieve", return_value=mock_payment_method),
    ):
        response = provider.process_data(payment, request)
        
        assert response.status_code == 200
        assert payment.status == PaymentStatus.CONFIRMED
        payment.set_renew_token.assert_called_once()


def test_process_data_checkout_session_expired():
    """Test processing checkout.session.expired webhook event."""
    payment = Payment()
    payment.token = "payment-token-123"
    
    provider = StripeProviderV3(api_key=API_KEY, endpoint_secret="whsec_test")
    
    event_data = {
        "type": "checkout.session.expired",
        "data": {
            "object": {
                "id": "cs_test_123",
                "status": "expired",
            }
        },
    }
    
    request = MockRequest(
        body=json.dumps(event_data).encode(),
        headers={"STRIPE_SIGNATURE": "test_sig"},
    )
    
    with patch("stripe.Webhook.construct_event", return_value=event_data):
        response = provider.process_data(payment, request)
        
        assert response.status_code == 200
        assert payment.status == PaymentStatus.REJECTED


def test_process_data_unknown_event_type():
    """Test that unknown event types are ignored."""
    payment = Payment()
    
    provider = StripeProviderV3(api_key=API_KEY, endpoint_secret="whsec_test")
    
    event_data = {
        "type": "payment_intent.succeeded",  # Not in stripe_enabled_events
        "data": {"object": {}},
    }
    
    request = MockRequest(
        body=json.dumps(event_data).encode(),
        headers={"STRIPE_SIGNATURE": "test_sig"},
    )
    
    with patch("stripe.Webhook.construct_event", return_value=event_data):
        response = provider.process_data(payment, request)
        
        assert response.status_code == 200
        # Status should not change for unknown events
        assert payment.status == PaymentStatus.WAITING


@pytest.mark.django_db
def test_webhook_flow_setup_intent_with_token_in_metadata():
    """Integration test: Full webhook flow for setup_intent.succeeded.
    
    This simulates the actual webhook flow:
    1. Checkout Session is created with payment_token in metadata
    2. SetupIntent is created and inherits metadata from session
    3. Stripe sends setup_intent.succeeded webhook
    4. get_token_from_request() extracts token from SetupIntent metadata
    5. Payment is found and process_data() is called
    6. Payment status is updated to CONFIRMED
    """
    payment = Payment()
    payment.token = "test-payment-token-123"
    payment.set_renew_token = Mock()
    
    provider = StripeProviderV3(
        api_key=API_KEY,
        endpoint_secret="whsec_test",
        store_payment_method=True,
        use_setup_mode=True,
    )
    
    # Simulate Stripe's setup_intent.succeeded webhook with token in metadata
    event_data = {
        "type": "setup_intent.succeeded",
        "data": {
            "object": {
                "id": "seti_test_123",
                "customer": "cus_test_123",
                "payment_method": "pm_test_123",
                "status": "succeeded",
                "metadata": {
                    "payment_token": "test-payment-token-123",  # Token stored in metadata
                },
            }
        },
    }
    
    mock_payment_method = Mock()
    mock_payment_method.type = "card"
    mock_payment_method.card = Mock()
    mock_payment_method.card.exp_year = 2025
    mock_payment_method.card.exp_month = 12
    mock_payment_method.card.last4 = "4242"
    
    request = MockRequest(
        body=json.dumps(event_data).encode(),
        headers={"STRIPE_SIGNATURE": "test_sig"},
    )
    
    with (
        patch("stripe.Webhook.construct_event", return_value=event_data),
        patch("stripe.PaymentMethod.retrieve", return_value=mock_payment_method),
    ):
        # Step 1: Extract token from webhook (simulates static_callback)
        token = provider.get_token_from_request(payment=None, request=request)
        assert token == "test-payment-token-123"
        
        # Step 2: Process the webhook (simulates process_data)
        response = provider.process_data(payment, request)
        
        # Step 3: Verify payment was updated correctly
        assert response.status_code == 200
        assert payment.status == PaymentStatus.CONFIRMED
        payment.set_renew_token.assert_called_once_with(
            token="pm_test_123",
            customer_id="cus_test_123",
            card_expire_year=2025,
            card_expire_month=12,
            card_masked_number="4242",
        )


@pytest.mark.django_db
def test_webhook_flow_setup_intent_with_session_lookup():
    """Integration test: Full webhook flow with Checkout Session lookup fallback.
    
    This simulates the scenario where SetupIntent metadata doesn't contain the
    payment_token (Stripe sometimes doesn't copy metadata), so we need to look
    up the Checkout Session to find the token.
    """
    payment = Payment()
    payment.token = "test-payment-token-456"
    payment.set_renew_token = Mock()
    
    provider = StripeProviderV3(
        api_key=API_KEY,
        endpoint_secret="whsec_test",
        store_payment_method=True,
        use_setup_mode=True,
    )
    
    # Simulate Stripe's setup_intent.succeeded webhook WITHOUT token in metadata
    event_data = {
        "type": "setup_intent.succeeded",
        "data": {
            "object": {
                "id": "seti_test_456",
                "customer": "cus_test_456",
                "payment_method": "pm_test_456",
                "status": "succeeded",
                "created": 1700000000,
                "metadata": {},  # Empty metadata - need to look up session
            }
        },
    }
    
    # Mock the Checkout Session that contains the payment token
    mock_session = {
        "mode": "setup",
        "client_reference_id": "test-payment-token-456",
        "metadata": {"payment_token": "test-payment-token-456"}
    }
    
    mock_payment_method = Mock()
    mock_payment_method.type = "card"
    mock_payment_method.card = Mock()
    mock_payment_method.card.exp_year = 2026
    mock_payment_method.card.exp_month = 6
    mock_payment_method.card.last4 = "1234"
    
    request = MockRequest(
        body=json.dumps(event_data).encode(),
        headers={"STRIPE_SIGNATURE": "test_sig"},
    )
    
    with (
        patch("stripe.Webhook.construct_event", return_value=event_data),
        patch("stripe.PaymentMethod.retrieve", return_value=mock_payment_method),
        patch(
            "stripe.checkout.Session.list",
            return_value=Mock(data=[mock_session]),
        ),
    ):
        # Step 1: Extract token from webhook (requires session lookup)
        token = provider.get_token_from_request(payment=None, request=request)
        assert token == "test-payment-token-456"
        
        # Step 2: Process the webhook
        response = provider.process_data(payment, request)
        
        # Step 3: Verify payment was updated correctly
        assert response.status_code == 200
        assert payment.status == PaymentStatus.CONFIRMED
        payment.set_renew_token.assert_called_once_with(
            token="pm_test_456",
            customer_id="cus_test_456",
            card_expire_year=2026,
            card_expire_month=6,
            card_masked_number="1234",
        )
