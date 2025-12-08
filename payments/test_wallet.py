"""
Tests for wallet-based recurring payments interface.

These tests verify the wallet interface using mocks, following the established
pattern from test_core.py.
"""
from decimal import Decimal
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from payments import PaymentError
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


def test_base_wallet_payment_completed_activates():
    """payment_completed() activates pending wallet on confirmed payment."""
    wallet = Wallet(status=WalletStatus.PENDING)
    payment = Payment(status=PaymentStatus.CONFIRMED)
    
    with patch.object(BaseWallet, "save"):
        wallet.payment_completed(payment)
    
    assert wallet.status == WalletStatus.ACTIVE


def test_base_wallet_payment_completed_ignores_non_confirmed():
    """payment_completed() doesn't activate on non-confirmed payments."""
    wallet = Wallet(status=WalletStatus.PENDING)
    payment = Payment(status=PaymentStatus.WAITING)
    
    wallet.payment_completed(payment)
    
    assert wallet.status == WalletStatus.PENDING


def test_base_wallet_activate():
    """activate() marks wallet as ACTIVE."""
    wallet = Wallet(status=WalletStatus.PENDING)
    
    with patch.object(BaseWallet, "save"):
        wallet.activate()
    
    assert wallet.status == WalletStatus.ACTIVE


def test_base_wallet_erase():
    """erase() marks wallet as ERASED."""
    wallet = Wallet(status=WalletStatus.ACTIVE, token="test_token")
    
    with patch.object(BaseWallet, "save"):
        wallet.erase()
    
    assert wallet.status == WalletStatus.ERASED
    assert wallet.token == "test_token"  # Token preserved for audit


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


def test_dummy_provider_autocomplete_with_wallet():
    """DummyProvider implements autocomplete_with_wallet."""
    provider = provider_factory("default")
    payment = Payment(
        variant="default",
        status=PaymentStatus.WAITING,
        total=Decimal("20.00"),
        currency="USD",
    )
    
    with patch.object(payment, "get_renew_token", return_value="test_token"):
        with patch.object(BasePayment, "save"):
            provider.autocomplete_with_wallet(payment)
    
    # DummyProvider should set these values
    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.captured_amount == Decimal("20.00")
    assert payment.transaction_id.startswith("dummy-wallet-charge-")


def test_autocomplete_with_wallet_without_token_fails():
    """autocomplete_with_wallet raises error without token."""
    provider = provider_factory("default")
    payment = Payment(
        variant="default",
        status=PaymentStatus.WAITING,
        total=Decimal("20.00"),
        currency="USD",
    )
    
    with patch.object(payment, "get_renew_token", return_value=None):
        with pytest.raises(PaymentError, match="No payment method token"):
            provider.autocomplete_with_wallet(payment)


def test_provider_finalize_wallet_payment():
    """_finalize_wallet_payment triggers wallet.payment_completed."""
    provider = provider_factory("default")
    wallet = Wallet(status=WalletStatus.PENDING)
    payment = Payment(status=PaymentStatus.CONFIRMED)
    payment.wallet = wallet
    
    with patch.object(wallet, "payment_completed") as mock_completed:
        provider._finalize_wallet_payment(payment)
    
    mock_completed.assert_called_once_with(payment)


def test_provider_finalize_wallet_payment_without_wallet():
    """_finalize_wallet_payment handles missing wallet gracefully."""
    provider = provider_factory("default")
    payment = Payment(status=PaymentStatus.CONFIRMED)
    payment.wallet = None
    
    # Should not raise
    provider._finalize_wallet_payment(payment)
