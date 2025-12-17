"""
Mock-based unit tests for subscription interface logic.

These tests verify the subscription interface using mocks, following the established
pattern from test_core.py and test_wallet.py. They test interface contracts and
simple logic without needing a database.

For integration tests that verify model lifecycle and provider workflows with
a real database, see testapp/testapp/testmain/test_subscription.py.
"""

from __future__ import annotations

from unittest.mock import Mock
from unittest.mock import patch

import pytest

from payments import PaymentError
from payments import PaymentStatus
from payments import SubscriptionStatus
from payments.core import provider_factory
from payments.models import BasePayment
from payments.models import BaseSubscription


class Subscription(BaseSubscription):
    """Test subscription model (not persisted to database)."""

    class Meta:
        app_label = "test_subscription"


class Payment(BasePayment):
    """Test payment model (not persisted to database)."""

    def get_subscription(self):
        """Override to support subscription retrieval for testing."""
        if hasattr(self, "subscription") and self.subscription:
            return self.subscription
        return None

    class Meta:
        app_label = "test_subscription"


def test_subscription_status_choices():
    """Verify SubscriptionStatus constants are defined."""
    assert SubscriptionStatus.PENDING == "pending"
    assert SubscriptionStatus.ACTIVE == "active"
    assert SubscriptionStatus.CANCELLED == "cancelled"
    assert SubscriptionStatus.EXPIRED == "expired"


def test_base_subscription_default_status():
    """New subscriptions start in PENDING status."""
    subscription = Subscription()
    assert subscription.status == SubscriptionStatus.PENDING


def test_subscription_activate():
    """Subscription.activate() marks subscription as ACTIVE."""
    subscription = Subscription(status=SubscriptionStatus.PENDING)
    with patch.object(BaseSubscription, "save"):
        subscription.activate()
    assert subscription.status == SubscriptionStatus.ACTIVE


def test_subscription_cancel():
    """Subscription.cancel() marks subscription as CANCELLED."""
    subscription = Subscription(status=SubscriptionStatus.ACTIVE)
    with patch.object(BaseSubscription, "save"):
        subscription.cancel()
    assert subscription.status == SubscriptionStatus.CANCELLED


def test_subscription_expire():
    """Subscription.expire() marks subscription as EXPIRED."""
    subscription = Subscription(status=SubscriptionStatus.ACTIVE)
    with patch.object(BaseSubscription, "save"):
        subscription.expire()
    assert subscription.status == SubscriptionStatus.EXPIRED


def test_subscription_payment_completed_activates_on_first_payment():
    """
    subscription_payment_completed activates subscription on first payment.
    """
    subscription = Subscription(status=SubscriptionStatus.PENDING)
    payment = Payment(status=PaymentStatus.CONFIRMED)

    with patch.object(BaseSubscription, "save"):
        subscription.subscription_payment_completed(payment)

    assert subscription.status == SubscriptionStatus.ACTIVE


def test_subscription_payment_completed_no_change_if_already_active():
    """subscription_payment_completed doesn't change status if already active."""
    subscription = Subscription(status=SubscriptionStatus.ACTIVE)
    payment = Payment(status=PaymentStatus.CONFIRMED)

    with patch.object(BaseSubscription, "save") as mock_save:
        subscription.subscription_payment_completed(payment)

    # Should not save since status didn't change
    mock_save.assert_not_called()


def test_subscription_payment_completed_no_change_if_not_confirmed():
    """subscription_payment_completed doesn't activate if payment not confirmed."""
    subscription = Subscription(status=SubscriptionStatus.PENDING)
    payment = Payment(status=PaymentStatus.WAITING)

    with patch.object(BaseSubscription, "save") as mock_save:
        subscription.subscription_payment_completed(payment)

    assert subscription.status == SubscriptionStatus.PENDING
    mock_save.assert_not_called()


def test_payment_get_subscription_default():
    """get_subscription() returns None by default."""
    payment = Payment()
    assert payment.get_subscription() is None


def test_payment_get_subscription_with_subscription():
    """get_subscription() returns subscription when available."""
    subscription = Mock()
    payment = Payment()
    payment.subscription = subscription

    assert payment.get_subscription() == subscription


def test_payment_cancel_subscription_calls_provider():
    """Payment.cancel_subscription() calls provider implementation."""
    subscription = Mock()
    payment = Payment(variant="default")
    payment.subscription = subscription

    with patch("payments.models.provider_factory") as mock_factory:
        mock_provider = Mock()
        mock_factory.return_value = mock_provider

        payment.cancel_subscription()

        mock_provider.cancel_subscription.assert_called_once_with(payment)


def test_payment_cancel_subscription_raises_without_subscription():
    """Payment.cancel_subscription() raises ValueError if no subscription."""
    payment = Payment(variant="default")
    payment.subscription = None

    with pytest.raises(ValueError, match="No subscription associated"):
        payment.cancel_subscription()


def test_payment_autocomplete_with_subscription_calls_provider():
    """Payment.autocomplete_with_subscription() calls provider implementation."""
    payment = Payment(variant="default")

    with patch("payments.models.provider_factory") as mock_factory:
        mock_provider = Mock()
        mock_factory.return_value = mock_provider

        payment.autocomplete_with_subscription()

        mock_provider.autocomplete_with_subscription.assert_called_once_with(payment)


def test_provider_finalize_subscription_payment_without_subscription():
    """_finalize_subscription_payment handles missing subscription gracefully."""
    provider = provider_factory("default")
    payment = Payment(status=PaymentStatus.CONFIRMED)
    payment.subscription = None

    # Should not raise
    provider._finalize_subscription_payment(payment)


def test_provider_finalize_subscription_payment_with_subscription():
    """
    _finalize_subscription_payment calls subscription payment hook.
    """
    provider = provider_factory("default")
    payment = Payment(status=PaymentStatus.CONFIRMED)
    subscription = Mock()
    payment.subscription = subscription

    provider._finalize_subscription_payment(payment)

    subscription.subscription_payment_completed.assert_called_once_with(payment)


def test_subscription_extra_data_stores_metadata():
    """Subscription extra_data can store provider-specific metadata."""
    subscription = Subscription(subscription_id="sub_test")
    subscription.extra_data = {
        "plan": "premium",
        "interval": "monthly",
        "next_billing_date": "2025-01-01",
        "stripe_customer_id": "cus_test",
    }

    assert subscription.extra_data["plan"] == "premium"
    assert subscription.extra_data["interval"] == "monthly"
    assert subscription.extra_data["stripe_customer_id"] == "cus_test"


def test_cancelled_subscription_preserves_data():
    """Cancelled subscription keeps subscription_id for audit purposes."""
    subscription = Subscription(
        status=SubscriptionStatus.ACTIVE,
        subscription_id="sub_historical",
        extra_data={"plan": "premium", "cancellation_reason": "user_request"},
    )

    with patch.object(BaseSubscription, "save"):
        subscription.cancel()

    assert subscription.status == SubscriptionStatus.CANCELLED
    assert subscription.subscription_id == "sub_historical"  # Preserved
    assert subscription.extra_data["plan"] == "premium"  # Preserved


def test_documentation_pattern_subscription_fk():
    """Document the simple subscription FK pattern."""
    subscription = Mock()
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.subscription_id = "sub_test"

    payment = Payment(variant="test")
    payment.subscription = subscription

    # get_subscription returns subscription
    result = payment.get_subscription()
    assert result == subscription


def test_subscription_lifecycle_pending_to_active():
    """Document subscription lifecycle: PENDING -> ACTIVE."""
    subscription = Subscription(status=SubscriptionStatus.PENDING)
    payment = Payment(status=PaymentStatus.CONFIRMED)

    with patch.object(BaseSubscription, "save"):
        subscription.subscription_payment_completed(payment)

    assert subscription.status == SubscriptionStatus.ACTIVE


def test_subscription_lifecycle_active_to_cancelled():
    """Document subscription lifecycle: ACTIVE -> CANCELLED."""
    subscription = Subscription(
        status=SubscriptionStatus.ACTIVE, subscription_id="sub_test"
    )

    with patch.object(BaseSubscription, "save"):
        subscription.cancel()

    assert subscription.status == SubscriptionStatus.CANCELLED


def test_subscription_lifecycle_active_to_expired():
    """Document subscription lifecycle: ACTIVE -> EXPIRED."""
    subscription = Subscription(
        status=SubscriptionStatus.ACTIVE, subscription_id="sub_test"
    )

    with patch.object(BaseSubscription, "save"):
        subscription.expire()

    assert subscription.status == SubscriptionStatus.EXPIRED


def test_provider_cancel_subscription_not_implemented():
    """BasicProvider.cancel_subscription raises NotImplementedError by default."""
    # DummyProvider implements this, so we need to test with BasicProvider
    from payments.core import BasicProvider

    payment = Payment(variant="default")
    basic_provider = BasicProvider()

    with pytest.raises(NotImplementedError):
        basic_provider.cancel_subscription(payment)


def test_provider_autocomplete_with_subscription_not_implemented():
    """
    BasicProvider.autocomplete_with_subscription raises NotImplementedError.
    """
    from payments.core import BasicProvider

    basic_provider = BasicProvider()
    payment = Payment(variant="default")

    with pytest.raises(NotImplementedError):
        basic_provider.autocomplete_with_subscription(payment)


def test_dummy_provider_cancel_subscription_raises_without_subscription():
    """DummyProvider.cancel_subscription raises if no subscription."""
    provider = provider_factory("default")
    payment = Payment(variant="default")
    payment.subscription = None

    with pytest.raises(PaymentError, match="No subscription associated"):
        provider.cancel_subscription(payment)


def test_dummy_provider_cancel_subscription_raises_without_subscription_id():
    """
    DummyProvider.cancel_subscription raises if not created with provider.
    """
    provider = provider_factory("default")
    subscription = Subscription(subscription_id="")
    payment = Payment(variant="default")
    payment.subscription = subscription

    with pytest.raises(PaymentError, match="not yet created"):
        provider.cancel_subscription(payment)


def test_dummy_provider_autocomplete_with_subscription_raises_without_subscription():
    """
    DummyProvider.autocomplete_with_subscription raises if no subscription.
    """
    provider = provider_factory("default")
    payment = Payment(variant="default")
    payment.subscription = None

    with pytest.raises(PaymentError, match="No subscription associated"):
        provider.autocomplete_with_subscription(payment)


def test_payment_get_subscription_returns_none_by_default():
    """BasePayment.get_subscription() returns None by default (line 490)."""
    # Create a BasePayment instance directly (not our test subclass)
    from payments.models import BasePayment

    class MinimalPayment(BasePayment):
        """Minimal payment without get_subscription override."""

        class Meta:
            app_label = "test_subscription"

    payment = MinimalPayment()
    # This tests line 490: return None
    assert payment.get_subscription() is None


def test_payment_cancel_subscription_full_flow():
    """Test cancel_subscription calls provider (lines 507-512)."""
    subscription = Mock()
    payment = Payment(variant="default")
    payment.subscription = subscription

    with patch("payments.models.provider_factory") as mock_factory:
        mock_provider = Mock()
        mock_factory.return_value = mock_provider

        # This tests lines 507-512
        payment.cancel_subscription()

        # Verify provider was called
        mock_factory.assert_called_once_with(payment.variant)
        mock_provider.cancel_subscription.assert_called_once_with(payment)


def test_payment_autocomplete_with_subscription_full_flow():
    """Test autocomplete_with_subscription calls provider (lines 535-536)."""
    payment = Payment(variant="default")

    with patch("payments.models.provider_factory") as mock_factory:
        mock_provider = Mock()
        mock_factory.return_value = mock_provider

        # This tests lines 535-536
        payment.autocomplete_with_subscription()

        # Verify provider was called
        mock_factory.assert_called_once_with(payment.variant)
        mock_provider.autocomplete_with_subscription.assert_called_once_with(payment)

