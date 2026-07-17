"""Unit tests for the wallet interface defaults.

Database-backed tests live in testapp/testapp/testmain/test_wallet.py.
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
    class Meta:
        app_label = "test_wallet"


class Payment(BasePayment):
    class Meta:
        app_label = "test_wallet"


def test_new_wallet_is_pending():
    assert Wallet().status == WalletStatus.PENDING


def test_get_renew_token_default_is_none():
    assert Payment().get_renew_token() is None


def test_set_renew_token_default_is_noop():
    Payment().set_renew_token("token", card_masked_number="4242")


def test_autocomplete_with_wallet_dispatches_to_provider():
    payment = Payment(variant="default")
    with patch("payments.models.provider_factory") as mock_factory:
        payment.autocomplete_with_wallet()
    mock_factory.return_value.autocomplete_with_wallet.assert_called_once_with(payment)


def test_finalize_wallet_payment_without_wallet():
    payment = Payment(status=PaymentStatus.CONFIRMED)
    provider_factory("default")._finalize_wallet_payment(payment)


def test_finalize_wallet_payment_notifies_wallet():
    payment = Payment(status=PaymentStatus.CONFIRMED)
    wallet = Mock()
    provider_factory("default")._finalize_wallet_payment(payment, wallet)
    wallet.payment_completed.assert_called_once_with(payment)


def test_erase_wallet_default_is_noop():
    provider_factory("default").erase_wallet("token")


def test_erase_keeps_token():
    wallet = Wallet(status=WalletStatus.ACTIVE, token="pm_1")
    with patch.object(BaseWallet, "save"):
        wallet.erase()
    assert wallet.status == WalletStatus.ERASED
    assert wallet.token == "pm_1"
