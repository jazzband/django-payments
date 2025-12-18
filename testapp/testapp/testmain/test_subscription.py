"""
Integration tests for subscription interface with real database.

These tests verify the subscription interface using real Payment and Subscription
models with database operations. They complement the mock-based tests in
payments/test_subscription.py.

These tests use Django's test framework and require database access.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import TestCase
from testmain.models import Payment
from testmain.models import Subscription

from payments import PaymentError
from payments import PaymentStatus
from payments import SubscriptionStatus
from payments.core import provider_factory


@pytest.mark.django_db
class TestSubscriptionModel(TestCase):
    """Test Subscription model lifecycle and state transitions."""

    def test_subscription_creation(self):
        """Subscription can be created with default status."""
        subscription = Subscription.objects.create(
            payment_provider="default", plan="basic"
        )

        assert subscription.status == SubscriptionStatus.PENDING
        assert subscription.subscription_id == ""
        assert subscription.plan == "basic"

    def test_subscription_activate(self):
        """Subscription.activate() updates status in database."""
        subscription = Subscription.objects.create(
            payment_provider="default", subscription_id="sub_test"
        )

        subscription.activate()
        subscription.refresh_from_db()

        assert subscription.status == SubscriptionStatus.ACTIVE

    def test_subscription_cancel(self):
        """Subscription.cancel() updates status in database."""
        subscription = Subscription.objects.create(
            payment_provider="default",
            subscription_id="sub_test",
            status=SubscriptionStatus.ACTIVE,
        )

        subscription.cancel()
        subscription.refresh_from_db()

        assert subscription.status == SubscriptionStatus.CANCELLED

    def test_subscription_expire(self):
        """Subscription.expire() updates status in database."""
        subscription = Subscription.objects.create(
            payment_provider="default",
            subscription_id="sub_test",
            status=SubscriptionStatus.ACTIVE,
        )

        subscription.expire()
        subscription.refresh_from_db()

        assert subscription.status == SubscriptionStatus.EXPIRED

    def test_subscription_payment_completed_activates(self):
        """subscription_payment_completed activates subscription on first payment."""
        subscription = Subscription.objects.create(
            payment_provider="default", subscription_id="sub_test"
        )
        payment = Payment.objects.create(
            variant="default",
            currency="USD",
            total=100,
            status=PaymentStatus.CONFIRMED,
            subscription=subscription,
        )

        subscription.subscription_payment_completed(payment)
        subscription.refresh_from_db()

        assert subscription.status == SubscriptionStatus.ACTIVE

    def test_subscription_extra_data_persistence(self):
        """Subscription extra_data persists to database."""
        subscription = Subscription.objects.create(
            payment_provider="default",
            subscription_id="sub_test",
            extra_data={
                "plan": "premium",
                "interval": "monthly",
                "next_billing_date": "2025-01-01",
            },
        )

        subscription.refresh_from_db()

        assert subscription.extra_data["plan"] == "premium"
        assert subscription.extra_data["interval"] == "monthly"


@pytest.mark.django_db
class TestPaymentSubscriptionIntegration(TestCase):
    """Test Payment model integration with Subscription."""

    def test_payment_get_subscription(self):
        """Payment.get_subscription() returns associated subscription."""
        subscription = Subscription.objects.create(
            payment_provider="default", subscription_id="sub_test"
        )
        payment = Payment.objects.create(
            variant="default", currency="USD", total=100, subscription=subscription
        )

        result = payment.get_subscription()

        assert result == subscription
        assert result.subscription_id == "sub_test"

    def test_payment_get_subscription_none(self):
        """Payment.get_subscription() returns None if no subscription."""
        payment = Payment.objects.create(variant="default", currency="USD", total=100)

        result = payment.get_subscription()

        assert result is None

    def test_payment_cancel_subscription_raises_without_subscription(self):
        """Payment.cancel_subscription() raises if no subscription."""
        payment = Payment.objects.create(variant="default", currency="USD", total=100)

        with pytest.raises(ValueError, match="No subscription associated"):
            payment.cancel_subscription()


@pytest.mark.django_db
class TestDummyProviderSubscription(TestCase):
    """Test DummyProvider subscription implementation with real models."""

    def test_autocomplete_with_subscription_creates_subscription_id(self):
        """DummyProvider.autocomplete_with_subscription creates subscription_id."""
        subscription = Subscription.objects.create(
            payment_provider="default", plan="basic"
        )
        payment = Payment.objects.create(
            variant="default", currency="USD", total=100, subscription=subscription
        )

        provider = provider_factory("default")
        provider.autocomplete_with_subscription(payment)

        subscription.refresh_from_db()
        payment.refresh_from_db()

        assert subscription.subscription_id.startswith("dummy-sub-")
        assert payment.status == PaymentStatus.CONFIRMED
        assert payment.captured_amount == 100
        assert payment.transaction_id.startswith("dummy-sub-charge-")

    def test_autocomplete_with_subscription_activates_subscription(self):
        """DummyProvider.autocomplete_with_subscription activates subscription."""
        subscription = Subscription.objects.create(
            payment_provider="default", plan="basic"
        )
        payment = Payment.objects.create(
            variant="default", currency="USD", total=100, subscription=subscription
        )

        provider = provider_factory("default")
        provider.autocomplete_with_subscription(payment)

        subscription.refresh_from_db()

        assert subscription.status == SubscriptionStatus.ACTIVE

    def test_autocomplete_with_subscription_raises_without_subscription(self):
        """DummyProvider.autocomplete_with_subscription raises if no subscription."""
        payment = Payment.objects.create(variant="default", currency="USD", total=100)

        provider = provider_factory("default")

        with pytest.raises(PaymentError, match="No subscription associated"):
            provider.autocomplete_with_subscription(payment)

    def test_cancel_subscription_updates_status(self):
        """DummyProvider.cancel_subscription updates subscription status."""
        subscription = Subscription.objects.create(
            payment_provider="default",
            subscription_id="sub_test",
            status=SubscriptionStatus.ACTIVE,
        )
        payment = Payment.objects.create(
            variant="default", currency="USD", total=100, subscription=subscription
        )

        provider = provider_factory("default")
        provider.cancel_subscription(payment)

        subscription.refresh_from_db()

        assert subscription.status == SubscriptionStatus.CANCELLED

    def test_cancel_subscription_raises_without_subscription(self):
        """DummyProvider.cancel_subscription raises if no subscription."""
        payment = Payment.objects.create(variant="default", currency="USD", total=100)

        provider = provider_factory("default")

        with pytest.raises(PaymentError, match="No subscription associated"):
            provider.cancel_subscription(payment)

    def test_cancel_subscription_raises_without_subscription_id(self):
        """DummyProvider.cancel_subscription raises if subscription not created."""
        subscription = Subscription.objects.create(
            payment_provider="default", subscription_id=""
        )
        payment = Payment.objects.create(
            variant="default", currency="USD", total=100, subscription=subscription
        )

        provider = provider_factory("default")

        with pytest.raises(PaymentError, match="not yet created"):
            provider.cancel_subscription(payment)


@pytest.mark.django_db
class TestSubscriptionWorkflow(TestCase):
    """Test complete subscription workflows."""

    def test_subscription_setup_and_first_payment(self):
        """Test complete subscription setup flow."""
        # 1. Create subscription
        subscription = Subscription.objects.create(
            payment_provider="default", plan="premium"
        )
        assert subscription.status == SubscriptionStatus.PENDING

        # 2. Create payment for subscription
        payment = Payment.objects.create(
            variant="default",
            currency="USD",
            total=Decimal("29.99"),
            subscription=subscription,
        )

        # 3. Complete subscription payment
        provider = provider_factory("default")
        provider.autocomplete_with_subscription(payment)

        # 4. Verify subscription is active
        subscription.refresh_from_db()
        payment.refresh_from_db()

        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.subscription_id.startswith("dummy-sub-")
        assert payment.status == PaymentStatus.CONFIRMED
        assert payment.captured_amount == Decimal("29.99")

    def test_subscription_recurring_payment(self):
        """Test recurring payment for active subscription."""
        # Setup: Active subscription with subscription_id
        subscription = Subscription.objects.create(
            payment_provider="default",
            plan="premium",
            subscription_id="sub_existing",
            status=SubscriptionStatus.ACTIVE,
        )

        # Simulate provider creating recurring payment
        payment = Payment.objects.create(
            variant="default",
            currency="USD",
            total=Decimal("29.99"),
            subscription=subscription,
        )

        # Complete payment (provider already has subscription_id)
        provider = provider_factory("default")
        provider.autocomplete_with_subscription(payment)

        payment.refresh_from_db()

        assert payment.status == PaymentStatus.CONFIRMED
        assert payment.captured_amount == Decimal("29.99")
        # Subscription stays active (already was)
        assert subscription.status == SubscriptionStatus.ACTIVE

    def test_subscription_cancellation(self):
        """Test subscription cancellation flow."""
        # Setup: Active subscription
        subscription = Subscription.objects.create(
            payment_provider="default",
            plan="premium",
            subscription_id="sub_active",
            status=SubscriptionStatus.ACTIVE,
        )
        payment = Payment.objects.create(
            variant="default",
            currency="USD",
            total=Decimal("29.99"),
            subscription=subscription,
        )

        # Cancel subscription
        payment.cancel_subscription()

        subscription.refresh_from_db()

        assert subscription.status == SubscriptionStatus.CANCELLED

    def test_subscription_with_variable_amounts(self):
        """Test subscription with different payment amounts (usage-based)."""
        subscription = Subscription.objects.create(
            payment_provider="default",
            plan="usage-based",
            subscription_id="sub_usage",
            status=SubscriptionStatus.ACTIVE,
        )

        # First payment: $10
        payment1 = Payment.objects.create(
            variant="default", currency="USD", total=10, subscription=subscription
        )
        provider = provider_factory("default")
        provider.autocomplete_with_subscription(payment1)

        payment1.refresh_from_db()
        assert payment1.captured_amount == 10

        # Second payment: $25 (different amount)
        payment2 = Payment.objects.create(
            variant="default", currency="USD", total=25, subscription=subscription
        )
        provider.autocomplete_with_subscription(payment2)

        payment2.refresh_from_db()
        assert payment2.captured_amount == 25

        # Both payments linked to same subscription
        assert payment1.subscription == payment2.subscription
