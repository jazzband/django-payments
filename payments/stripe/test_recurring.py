"""
Tests for Stripe recurring payments (autocomplete_with_wallet).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import TestCase
from testmain.models import Payment
from testmain.models import Wallet

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded

from .providers import StripeProviderV3

API_KEY = "sk_test_4eC39HqLyjWDarjtT1zdp7dc"


class MockStripeIntent(dict):
    """
    JSON-serializable mock for Stripe PaymentIntent objects.

    Stripe objects are dict-like and JSON-serializable. This mock replicates
    that behavior so tests can store intents in payment.attrs without
    triggering "Object of type Mock is not JSON serializable" errors.
    """

    def __getattr__(self, key):
        try:
            value = self[key]
            # Recursively wrap nested dicts for attribute access
            if isinstance(value, dict):
                return MockStripeIntent(value)
            return value
        except KeyError as e:
            raise AttributeError(key) from e


class StripeRecurringPaymentTests(TestCase):
    """Test server-initiated recurring payments using stored payment methods."""

    def setUp(self):
        self.provider = StripeProviderV3(
            api_key=API_KEY, recurring_payments=True, secure_endpoint=False
        )
        self.wallet = Wallet.objects.create(payment_provider="stripe-recurring")
        # Set up wallet with stored payment method and customer
        self.wallet.token = "pm_test_456"
        self.wallet.extra_data = {"customer_id": "cus_test_123"}
        self.wallet.activate()
        self.wallet.save()

    @patch("stripe.PaymentIntent.create")
    def test_autocomplete_with_wallet_success(self, mock_pi_create):
        """Successful recurring charge using stored payment method."""
        # Create payment with wallet
        payment = Payment.objects.create(
            variant="stripe-recurring",
            total=Decimal("50.00"),
            currency="USD",
            wallet=self.wallet,
        )

        # Mock successful PaymentIntent
        mock_pi_create.return_value = MockStripeIntent(
            {
                "id": "pi_test_123",
                "status": "succeeded",
            }
        )

        # Execute recurring charge
        self.provider.autocomplete_with_wallet(payment)

        # Verify PaymentIntent was created correctly
        mock_pi_create.assert_called_once()
        call_kwargs = mock_pi_create.call_args[1]
        assert call_kwargs["amount"] == 5000  # $50.00 in cents
        assert call_kwargs["currency"] == "usd"
        assert call_kwargs["customer"] == "cus_test_123"
        assert call_kwargs["payment_method"] == "pm_test_456"
        assert call_kwargs["confirm"]
        assert call_kwargs["off_session"]

        # Verify payment status updated
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CONFIRMED
        assert payment.transaction_id == "pi_test_123"

    @patch("stripe.PaymentIntent.create")
    def test_autocomplete_with_wallet_missing_customer_id(self, mock_pi_create):
        """Should fail fast if customer_id not provided."""
        payment = Payment.objects.create(
            variant="stripe-recurring",
            total=Decimal("50.00"),
            currency="USD",
            wallet=self.wallet,
        )

        # Payment returns token but no customer_id
        with patch.object(payment, "get_renew_data", return_value={"token": "pm_test"}):
            with pytest.raises(PaymentError) as exc_info:
                self.provider.autocomplete_with_wallet(payment)

            assert "customer_id" in str(exc_info.value)
            assert "must be stored" in str(exc_info.value)

        # Should not attempt to create PaymentIntent
        mock_pi_create.assert_not_called()

    @patch("stripe.PaymentIntent.create")
    def test_autocomplete_with_wallet_requires_3ds(self, mock_pi_create):
        """Should raise RedirectNeeded when 3D Secure authentication required."""
        payment = Payment.objects.create(
            variant="stripe-recurring",
            total=Decimal("50.00"),
            currency="USD",
            wallet=self.wallet,
        )

        # Mock PaymentIntent requiring 3DS
        mock_pi_create.return_value = MockStripeIntent(
            {
                "id": "pi_test_123",
                "status": "requires_action",
                "next_action": {
                    "type": "redirect_to_url",
                    "redirect_to_url": {"url": "https://stripe.com/3ds/authenticate"},
                },
            }
        )

        # Should raise RedirectNeeded
        with pytest.raises(RedirectNeeded) as exc_info:
            self.provider.autocomplete_with_wallet(payment)

        assert str(exc_info.value) == "https://stripe.com/3ds/authenticate"

    @patch("stripe.PaymentIntent.create")
    def test_autocomplete_with_wallet_card_declined(self, mock_pi_create):
        """Should handle card declined gracefully."""
        payment = Payment.objects.create(
            variant="stripe-recurring",
            total=Decimal("50.00"),
            currency="USD",
            wallet=self.wallet,
        )

        # Mock declined payment
        mock_pi_create.return_value = MockStripeIntent(
            {
                "id": "pi_test_123",
                "status": "requires_payment_method",
                "last_payment_error": {"message": "Your card was declined"},
            }
        )

        # Execute - should not raise
        self.provider.autocomplete_with_wallet(payment)

        # Verify payment marked as rejected
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.REJECTED

    @patch("stripe.PaymentIntent.create")
    def test_autocomplete_with_wallet_stripe_error(self, mock_pi_create):
        """Should handle Stripe API errors."""
        import stripe

        payment = Payment.objects.create(
            variant="stripe-recurring",
            total=Decimal("50.00"),
            currency="USD",
            wallet=self.wallet,
        )

        # Mock Stripe error
        mock_pi_create.side_effect = stripe.error.CardError(
            message="Insufficient funds",
            param="card",
            code="card_declined",
        )

        # Should raise PaymentError
        with pytest.raises(PaymentError) as exc_info:
            self.provider.autocomplete_with_wallet(payment)

        assert "Card declined" in str(exc_info.value)

        # Payment should be marked as rejected
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.REJECTED

    def test_autocomplete_with_wallet_no_token(self):
        """Should fail if no payment method token available."""
        payment = Payment.objects.create(
            variant="stripe-recurring",
            total=Decimal("50.00"),
            currency="USD",
            wallet=self.wallet,
        )

        # Wallet has no token stored
        with patch.object(payment, "get_renew_data", return_value=None):
            with pytest.raises(PaymentError) as exc_info:
                self.provider.autocomplete_with_wallet(payment)

            assert "No payment method token" in str(exc_info.value)

    @patch("stripe.PaymentIntent.create")
    def test_autocomplete_with_wallet_includes_description(self, mock_pi_create):
        """Payment description should be included in PaymentIntent."""
        payment = Payment.objects.create(
            variant="stripe-recurring",
            total=Decimal("75.00"),
            currency="USD",
            wallet=self.wallet,
            description="Monthly subscription renewal - Premium Plan",
        )

        mock_pi_create.return_value = MockStripeIntent(
            {
                "id": "pi_test_desc",
                "status": "succeeded",
            }
        )

        self.provider.autocomplete_with_wallet(payment)

        # Verify description was included in PaymentIntent creation
        mock_pi_create.assert_called_once()
        call_kwargs = mock_pi_create.call_args[1]
        assert (
            call_kwargs["description"] == "Monthly subscription renewal - Premium Plan"
        )

    @patch("stripe.PaymentIntent.create")
    def test_autocomplete_with_wallet_without_description(self, mock_pi_create):
        """PaymentIntent should work without description (backward compatibility)."""
        payment = Payment.objects.create(
            variant="stripe-recurring",
            total=Decimal("25.00"),
            currency="USD",
            wallet=self.wallet,
            description="",  # Empty description
        )

        mock_pi_create.return_value = MockStripeIntent(
            {
                "id": "pi_test_no_desc",
                "status": "succeeded",
            }
        )

        self.provider.autocomplete_with_wallet(payment)

        # Verify description was not included when empty
        mock_pi_create.assert_called_once()
        call_kwargs = mock_pi_create.call_args[1]
        assert "description" not in call_kwargs
