from __future__ import annotations

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
    
    # metadata should not be present if no billing data
    assert "metadata" not in call_kwargs


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
