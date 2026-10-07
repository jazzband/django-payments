"""
Integration tests for wallet-based recurring payments.

These tests verify the wallet interface with real database operations and
model lifecycle. They complement the mock-based unit tests in
payments/test_wallet.py by testing:
- Real model state transitions with database saves
- Full provider workflows with real Payment/Wallet instances
- End-to-end payment scenarios with DB verification
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import TestCase
from testmain.models import Payment
from testmain.models import Wallet

from payments import PaymentError
from payments import PaymentStatus
from payments import WalletStatus
from payments.core import provider_factory


class WalletStateTransitionTests(TestCase):
    """Test wallet state transitions with real database operations."""

    def test_base_wallet_payment_completed_activates(self):
        """payment_completed() activates pending wallet on confirmed payment."""
        wallet = Wallet.objects.create(payment_provider="test")
        payment = Payment.objects.create(
            variant="default",
            status=PaymentStatus.CONFIRMED,
            total=Decimal("20.00"),
            currency="USD",
        )

        wallet.payment_completed(payment)

        # Verify DB state
        wallet.refresh_from_db()
        assert wallet.status == WalletStatus.ACTIVE

    def test_base_wallet_payment_completed_ignores_non_confirmed(self):
        """payment_completed() doesn't activate on non-confirmed payments."""
        wallet = Wallet.objects.create(payment_provider="test")
        payment = Payment.objects.create(
            variant="default",
            status=PaymentStatus.WAITING,
            total=Decimal("20.00"),
            currency="USD",
        )

        wallet.payment_completed(payment)

        # Verify DB state unchanged
        wallet.refresh_from_db()
        assert wallet.status == WalletStatus.PENDING

    def test_base_wallet_activate(self):
        """activate() marks wallet as ACTIVE."""
        wallet = Wallet.objects.create(payment_provider="test")

        wallet.activate()

        # Verify DB state
        wallet.refresh_from_db()
        assert wallet.status == WalletStatus.ACTIVE

    def test_base_wallet_erase(self):
        """erase() marks wallet as ERASED."""
        wallet = Wallet.objects.create(
            payment_provider="test",
            token="test_token",
            status=WalletStatus.ACTIVE,
        )

        wallet.erase()

        # Verify DB state
        wallet.refresh_from_db()
        assert wallet.status == WalletStatus.ERASED
        assert wallet.token == "test_token"  # Token preserved for audit

    def test_base_wallet_payment_completed_already_active(self):
        """payment_completed() doesn't change status if already active."""
        wallet = Wallet.objects.create(
            payment_provider="test", status=WalletStatus.ACTIVE
        )
        payment = Payment.objects.create(
            variant="default",
            status=PaymentStatus.CONFIRMED,
            total=Decimal("20.00"),
            currency="USD",
        )

        wallet.payment_completed(payment)

        # Verify status unchanged
        wallet.refresh_from_db()
        assert wallet.status == WalletStatus.ACTIVE


class DummyProviderWorkflowTests(TestCase):
    """Test DummyProvider wallet workflows with real models."""

    def test_dummy_provider_autocomplete_with_wallet(self):
        """DummyProvider implements autocomplete_with_wallet."""
        provider = provider_factory("default")
        wallet = Wallet.objects.create(
            payment_provider="default",
            token="test_token",
            status=WalletStatus.ACTIVE,
        )
        payment = Payment.objects.create(
            variant="default",
            status=PaymentStatus.WAITING,
            total=Decimal("20.00"),
            currency="USD",
            wallet=wallet,
        )

        provider.autocomplete_with_wallet(payment)

        # Verify DB state
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CONFIRMED
        assert payment.captured_amount == Decimal("20.00")
        assert payment.transaction_id.startswith("dummy-wallet-charge-")

    def test_autocomplete_with_wallet_without_token_fails(self):
        """autocomplete_with_wallet raises error without token."""
        provider = provider_factory("default")
        wallet = Wallet.objects.create(
            payment_provider="default",
            status=WalletStatus.ACTIVE,  # Active wallet but no token
            token="",  # Empty token
        )
        payment = Payment.objects.create(
            variant="default",
            status=PaymentStatus.WAITING,
            total=Decimal("20.00"),
            currency="USD",
            wallet=wallet,
        )

        with pytest.raises(PaymentError, match="No payment method token"):
            provider.autocomplete_with_wallet(payment)

    def test_dummy_provider_inactive_wallet_no_token(self):
        """Payment.get_renew_token() returns None for inactive wallets."""
        provider = provider_factory("default")
        wallet = Wallet.objects.create(
            payment_provider="default",
            token="test_token",
            status=WalletStatus.PENDING,  # Not active
        )
        payment = Payment.objects.create(
            variant="default",
            status=PaymentStatus.WAITING,
            total=Decimal("20.00"),
            currency="USD",
            wallet=wallet,
        )

        # get_renew_token() returns None for PENDING wallets (security feature)
        # So DummyProvider raises error about missing token
        with pytest.raises(PaymentError, match="No payment method token"):
            provider.autocomplete_with_wallet(payment)

    def test_provider_finalize_wallet_payment(self):
        """_finalize_wallet_payment triggers wallet.payment_completed."""
        provider = provider_factory("default")
        wallet = Wallet.objects.create(payment_provider="default")
        payment = Payment.objects.create(
            variant="default",
            status=PaymentStatus.CONFIRMED,
            total=Decimal("20.00"),
            currency="USD",
            wallet=wallet,
        )

        provider._finalize_wallet_payment(payment)

        # Verify wallet was activated
        wallet.refresh_from_db()
        assert wallet.status == WalletStatus.ACTIVE


class EndToEndWorkflowTests(TestCase):
    """Test complete payment workflows with real database state."""

    def test_first_payment_workflow(self):
        """Test complete first payment workflow."""
        provider = provider_factory("default")
        wallet = Wallet.objects.create(
            payment_provider="default", status=WalletStatus.PENDING
        )
        payment = Payment.objects.create(
            variant="default",
            status=PaymentStatus.WAITING,
            total=Decimal("29.99"),
            currency="USD",
            wallet=wallet,
        )

        # Simulate payment completion
        payment.status = PaymentStatus.CONFIRMED
        payment.save()

        # Provider should finalize (trigger wallet activation)
        provider._finalize_wallet_payment(payment)

        # Verify DB state
        wallet.refresh_from_db()
        assert wallet.status == WalletStatus.ACTIVE

    def test_recurring_payment_workflow(self):
        """Test recurring payment with stored token."""
        provider = provider_factory("default")
        wallet = Wallet.objects.create(
            payment_provider="default",
            token="stored_pm_token",
            status=WalletStatus.ACTIVE,
        )
        payment = Payment.objects.create(
            variant="default",
            status=PaymentStatus.WAITING,
            total=Decimal("35.00"),  # Different amount than first payment
            currency="USD",
            wallet=wallet,
        )

        provider.autocomplete_with_wallet(payment)

        # Verify DB state
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CONFIRMED
        assert payment.captured_amount == Decimal("35.00")

    def test_variable_amount_charges(self):
        """Wallet supports charging different amounts."""
        provider = provider_factory("default")
        wallet = Wallet.objects.create(
            payment_provider="default",
            token="pm_token",
            status=WalletStatus.ACTIVE,
        )

        # First charge: $20
        payment1 = Payment.objects.create(
            variant="default",
            total=Decimal("20.00"),
            currency="USD",
            wallet=wallet,
        )
        provider.autocomplete_with_wallet(payment1)

        # Verify first charge
        payment1.refresh_from_db()
        assert payment1.captured_amount == Decimal("20.00")

        # Second charge: $35 (different amount!)
        payment2 = Payment.objects.create(
            variant="default",
            total=Decimal("35.00"),
            currency="USD",
            wallet=wallet,
        )
        provider.autocomplete_with_wallet(payment2)

        # Verify second charge
        payment2.refresh_from_db()
        assert payment2.captured_amount == Decimal("35.00")
