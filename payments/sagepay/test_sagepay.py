from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from payments import PaymentStatus

from . import SagepayProvider

VENDOR = "abcd1234"
ENCRYPTION_KEY = "1234abdd1234abcd"


class Payment(Mock):
    id = 1
    variant = "sagepay"
    currency = "USD"
    total = 100
    status = PaymentStatus.WAITING
    transaction_id = None
    captured_amount = 0
    billing_first_name = "John"

    def get_process_url(self):
        return "http://example.com"

    def get_failure_url(self):
        return "http://cancel.com"

    def get_success_url(self):
        return "http://success.com"

    def change_status(self, status):
        self.status = status


@pytest.fixture
def payment():
    return Payment()


@pytest.fixture
def provider():
    return SagepayProvider(vendor=VENDOR, encryption_key=ENCRYPTION_KEY)


@patch("payments.sagepay.redirect")
def test_provider_raises_redirect_needed_on_success(mocked_redirect, payment, provider):
    data = {"Status": "OK"}
    data = "&".join("{}={}".format(*kv) for kv in data.items())
    with patch.object(SagepayProvider, "aes_dec", return_value=data):
        provider.process_data(payment, MagicMock())
        assert payment.status == PaymentStatus.CONFIRMED
        assert payment.captured_amount == payment.total


@patch("payments.sagepay.redirect")
def test_provider_raises_redirect_needed_on_failure(mocked_redirect, payment, provider):
    data = {"Status": ""}
    data = "&".join("{}={}".format(*kv) for kv in data.items())
    with patch.object(SagepayProvider, "aes_dec", return_value=data):
        provider.process_data(payment, MagicMock())
        assert payment.status == PaymentStatus.REJECTED
        assert payment.captured_amount == 0


def test_provider_encrypts_data(payment, provider):
    data = provider.get_hidden_fields(payment)
    decrypted_data = provider.aes_dec(data["Crypt"])
    assert payment.billing_first_name in str(decrypted_data)


def test_encrypt_method_returns_valid_data(provider):
    encrypted = provider.aes_enc("mirumee")
    assert encrypted == b"@e63c293672f50b9c8e291831facb4e4f"
