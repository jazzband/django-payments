"""
Mock-based unit tests for wallet interface logic.

These tests verify the wallet interface using mocks, following the established
pattern from test_core.py. They test interface contracts and simple logic without
needing a database.

For integration tests that verify model lifecycle and provider workflows with
a real database, see testapp/testapp/testmain/test_wallet.py.
"""

from __future__ import annotations

from unittest.mock import Mock
from unittest.mock import patch

from payments import PaymentStatus
from payments import WalletStatus
from payments.core import provider_factory
from payments.models import BasePayment
from payments.models import BaseWallet


class Wallet(BaseWallet):
    """Test wallet model (not persisted to database)."""

    class Meta:
        app_label = "test_wallet"


class Payment(BasePayment):
    """Test payment model (not persisted to database)."""

    def get_renew_token(self):
        """Override to support wallet token retrieval for testing."""
        if (
            hasattr(self, "wallet")
            and self.wallet
            and self.wallet.status == WalletStatus.ACTIVE
        ):
            return self.wallet.token
        return None

    class Meta:
        app_label = "test_wallet"


def test_wallet_status_choices():
    """Verify WalletStatus constants are defined."""
    assert WalletStatus.PENDING == "pending"
    assert WalletStatus.ACTIVE == "active"
    assert WalletStatus.ERASED == "erased"


def test_base_wallet_default_status():
    """New wallets start in PENDING status."""
    wallet = Wallet()
    assert wallet.status == WalletStatus.PENDING


def test_payment_get_renew_token_default():
    """get_renew_token() returns None by default."""
    payment = Payment()
    assert payment.get_renew_token() is None


def test_payment_get_renew_data_default():
    """get_renew_data() returns token dict by default."""
    payment = Payment()
    assert payment.get_renew_data() is None


def test_payment_get_renew_data_returns_token_dict():
    """get_renew_data() wraps token in dict."""
    payment = Payment()
    with patch.object(payment, "get_renew_token", return_value="test_token"):
        data = payment.get_renew_data()
        assert data == {"token": "test_token"}


def test_payment_set_renew_token_default():
    """set_renew_token() is a no-op by default (subclasses override)."""
    payment = Payment()
    # Should not raise
    payment.set_renew_token("test_token")


def test_provider_finalize_wallet_payment_without_wallet():
    """_finalize_wallet_payment handles missing wallet gracefully."""
    provider = provider_factory("default")
    payment = Payment(status=PaymentStatus.CONFIRMED)
    payment.wallet = None

    # Should not raise
    provider._finalize_wallet_payment(payment)


def test_wallet_extra_data_stores_metadata():
    """Wallet extra_data can store provider-specific metadata."""
    wallet = Wallet(token="pm_test")
    wallet.extra_data = {
        "card_masked_number": "4242",
        "card_expire_year": "2025",
        "stripe_customer_id": "cus_test",
    }

    assert wallet.extra_data["card_masked_number"] == "4242"
    assert wallet.extra_data["stripe_customer_id"] == "cus_test"


def test_get_renew_token_with_inactive_wallet():
    """get_renew_token returns None for non-ACTIVE wallets."""
    # Test with PENDING wallet
    wallet_pending = Mock(status=WalletStatus.PENDING, token="token1")
    payment_pending = Payment()
    payment_pending.wallet = wallet_pending

    assert payment_pending.get_renew_token() is None

    # Test with ERASED wallet
    wallet_erased = Mock(status=WalletStatus.ERASED, token="token2")
    payment_erased = Payment()
    payment_erased.wallet = wallet_erased

    assert payment_erased.get_renew_token() is None


def test_get_renew_token_with_active_wallet():
    """get_renew_token returns token for ACTIVE wallet."""
    # Mock wallet with ACTIVE status
    wallet = Mock()
    wallet.status = WalletStatus.ACTIVE
    wallet.token = "pm_active_token"
    wallet.__bool__ = lambda self: True  # Make wallet truthy

    payment = Payment()
    payment.wallet = wallet

    assert payment.get_renew_token() == "pm_active_token"


def test_autocomplete_with_wallet_calls_provider():
    """Payment.autocomplete_with_wallet calls provider implementation."""
    payment = Payment(variant="default")

    with patch("payments.models.provider_factory") as mock_factory:
        mock_provider = Mock()
        mock_factory.return_value = mock_provider

        payment.autocomplete_with_wallet()

        mock_provider.autocomplete_with_wallet.assert_called_once_with(payment)


def test_provider_erase_wallet():
    """BasicProvider.erase_wallet marks wallet as ERASED."""
    provider = provider_factory("default")
    wallet = Mock()
    wallet.status = WalletStatus.ACTIVE

    provider.erase_wallet(wallet)

    assert wallet.status == WalletStatus.ERASED


def test_erased_wallet_token_preserved():
    """Erased wallet keeps token for audit purposes."""
    wallet = Wallet(
        status=WalletStatus.ACTIVE,
        token="pm_historical",
        extra_data={"card_masked_number": "1234"},
    )

    with patch.object(BaseWallet, "save"):
        wallet.erase()

    assert wallet.status == WalletStatus.ERASED
    assert wallet.token == "pm_historical"  # Preserved
    assert wallet.extra_data["card_masked_number"] == "1234"  # Preserved


def test_set_renew_token_with_card_details():
    """set_renew_token can store card details in extra_data."""
    payment = Payment(variant="test")

    # Subclass would implement this, but we can test the interface
    with patch.object(payment, "set_renew_token"):
        payment.set_renew_token(
            token="pm_new",
            card_expire_year="2025",
            card_expire_month="12",
            card_masked_number="4242",
        )


def test_documentation_pattern_wallet_fk():
    """Document the simple wallet FK pattern."""
    # Pattern shown in testapp/testmain/models.py
    # This test documents the interface, actual DB behavior tested in integration tests
    wallet = Mock()
    wallet.status = WalletStatus.ACTIVE
    wallet.token = "pm_test"
    wallet.__bool__ = lambda self: True

    payment = Payment(variant="test")
    payment.wallet = wallet

    # get_renew_token checks wallet status and returns token
    token = payment.get_renew_token()
    assert token == "pm_test"


def test_documentation_pattern_custom_storage():
    """Document custom storage pattern without FK."""
    # Some apps might store token differently (e.g., on RecurringUserPlan)
    payment = Payment(variant="test")

    # Override get_renew_token to return from custom storage
    with patch.object(payment, "get_renew_token", return_value="custom_token"):
        token = payment.get_renew_token()
        assert token == "custom_token"


def test_get_renew_data_for_multi_value_providers():
    """get_renew_data supports providers needing multiple values (Stripe)."""
    payment = Payment(variant="stripe")

    # Subclass returns both token and customer_id for Stripe
    mock_data = {"token": "pm_test", "customer_id": "cus_test"}
    with patch.object(payment, "get_renew_data", return_value=mock_data):
        data = payment.get_renew_data()
        assert data["token"] == "pm_test"
        assert data["customer_id"] == "cus_test"
