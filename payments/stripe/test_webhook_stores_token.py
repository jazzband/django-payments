"""
Test that reproduces the issue: webhook arrives but token not stored.
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import Mock
from unittest.mock import patch

from django.test import RequestFactory
from django.test import TestCase
from testmain.models import Payment
from testmain.models import Wallet

from payments import PaymentStatus

from .providers import StripeProviderV3

API_KEY = "sk_test_4eC39HqLyjWDarjtT1zdp7dc"


class WebhookTokenStorageTest(TestCase):
    """Test webhook handler stores PaymentMethod token correctly."""

    def setUp(self):
        self.provider = StripeProviderV3(
            api_key=API_KEY, recurring_payments=True, secure_endpoint=False
        )
        self.factory = RequestFactory()

    @patch("stripe.PaymentMethod.retrieve")
    @patch("stripe.PaymentIntent.retrieve")
    def test_webhook_stores_token_in_wallet(self, mock_pi_retrieve, mock_pm_retrieve):
        """
        Webhook with checkout.session.completed should store PaymentMethod token.

        This reproduces the user's issue where payment succeeds but token not stored.
        """
        # Create wallet and payment
        wallet = Wallet.objects.create(payment_provider="stripe-recurring")
        payment = Payment.objects.create(
            variant="stripe-recurring",
            total=Decimal("130.68"),
            currency="USD",
            wallet=wallet,
            transaction_id="cs_test_abc123",
        )

        # Mock Stripe API responses
        mock_pi_retrieve.return_value = Mock(
            payment_method="pm_test_token_123", customer="cus_test_customer_123"
        )
        mock_pm_retrieve.return_value = Mock(
            type="card", card=Mock(exp_year=2025, exp_month=12, last4="4242")
        )

        # Simulate webhook from Stripe (real payload structure)
        webhook_payload = {
            "id": "evt_test_123",
            "object": "event",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_abc123",
                    "object": "checkout.session",
                    "payment_intent": "pi_test_intent_123",
                    "payment_status": "paid",
                    "status": "complete",
                    "client_reference_id": payment.token,
                }
            },
        }

        request = self.factory.post(
            "/payments/process/stripe-recurring/",
            data=json.dumps(webhook_payload),
            content_type="application/json",
        )

        # Process webhook
        self.provider.process_data(payment, request)

        # Verify payment confirmed
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CONFIRMED

        # Verify token stored in wallet
        wallet.refresh_from_db()
        assert wallet.token == "pm_test_token_123"
        assert wallet.extra_data["card_masked_number"] == "4242"
        assert wallet.extra_data["card_expire_year"] == 2025

    def test_store_payment_method_flag_is_set(self):
        """Verify recurring_payments=True sets store_payment_method=True."""
        provider = StripeProviderV3(api_key=API_KEY, recurring_payments=True)
        assert provider.store_payment_method

    def test_payment_has_set_renew_token_method(self):
        """Verify Payment model has set_renew_token method."""
        payment = Payment.objects.create(
            variant="stripe-recurring", total=Decimal("20.00"), currency="USD"
        )
        assert hasattr(payment, "set_renew_token")
        assert callable(payment.set_renew_token)
