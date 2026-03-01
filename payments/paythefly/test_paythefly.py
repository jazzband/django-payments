from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.http import HttpResponseForbidden

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded

from . import PayTheFlyProvider
from . import _amount_to_wei
from . import _verify_webhook_signature

# Test constants
PROJECT_ID = "test-project-123"
PROJECT_KEY = "test-secret-key-abc"
PRIVATE_KEY = "0x4c0883a69102937d6231471b5dbb6204fe512961708279f9d2e14a7b9c8e3b4a"
VERIFYING_CONTRACT = "0x1234567890AbCdEf1234567890aBcDeF12345678"
PAYMENT_TOKEN = "5a4dae68-2715-4b1e-8bb2-2c2dbe9255f6"
VARIANT = "paythefly"


class PaymentAttributeProxy:
    """Simple attribute proxy mimicking payments.models.PaymentAttributeProxy."""

    def __init__(self):
        self._data = {}

    def __getattr__(self, item):
        if item == "_data":
            return super().__getattribute__(item)
        try:
            return self._data[item]
        except KeyError as e:
            raise AttributeError(*e.args) from e

    def __setattr__(self, key, value):
        if key == "_data":
            return super().__setattr__(key, value)
        self._data[key] = value


class Payment:
    """Mock Payment object matching the django-payments BasePayment interface."""

    id = 1
    pk = 1
    description = "Test payment"
    currency = "BNB"
    total = Decimal("0.01")
    status = PaymentStatus.WAITING
    token = PAYMENT_TOKEN
    variant = VARIANT
    transaction_id = ""
    captured_amount = Decimal("0")
    extra_data = ""
    message = ""

    def __init__(self):
        self.attrs = PaymentAttributeProxy()

    def change_status(self, status, message=""):
        self.status = status
        self.message = message

    def get_failure_url(self):
        return "http://example.com/failure/"

    def get_success_url(self):
        return "http://example.com/success/"

    def get_process_url(self):
        return f"/payments/process/{self.token}/"

    def get_purchased_items(self):
        return []

    def save(self, **kwargs):
        return self


def _make_provider(**overrides):
    """Create a PayTheFlyProvider with test defaults."""
    kwargs = {
        "project_id": PROJECT_ID,
        "project_key": PROJECT_KEY,
        "private_key": PRIVATE_KEY,
        "verifying_contract": VERIFYING_CONTRACT,
        "chain_id": 56,
    }
    kwargs.update(overrides)
    return PayTheFlyProvider(**kwargs)


def _make_webhook_body(
    payment: Payment,
    tx_type: int = 1,
    confirmed: bool = True,
    tx_hash: str = "0xabc123def456",
) -> bytes:
    """Build a valid PayTheFly webhook request body."""
    data_dict = {
        "project_id": PROJECT_ID,
        "chain_symbol": "BSC",
        "tx_hash": tx_hash,
        "wallet": "0xSenderWallet",
        "value": str(payment.total),
        "fee": "0.0001",
        "serial_no": payment.token,
        "tx_type": tx_type,
        "confirmed": confirmed,
        "create_at": int(time.time()),
    }
    data_str = json.dumps(data_dict)
    timestamp = int(time.time())
    message = f"{data_str}.{timestamp}"
    sign = hmac.new(
        PROJECT_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return json.dumps({"data": data_str, "sign": sign, "timestamp": timestamp}).encode()


# --- Unit tests for helper functions ---


class TestAmountToWei:
    def test_bsc_18_decimals(self):
        result = _amount_to_wei(Decimal("0.01"), 18)
        assert result == 10000000000000000

    def test_tron_6_decimals(self):
        result = _amount_to_wei(Decimal("0.01"), 6)
        assert result == 10000

    def test_whole_number(self):
        result = _amount_to_wei(Decimal("1"), 18)
        assert result == 10**18

    def test_zero(self):
        result = _amount_to_wei(Decimal("0"), 18)
        assert result == 0


class TestVerifyWebhookSignature:
    def test_valid_signature(self):
        data = '{"key": "value"}'
        timestamp = 1700000000
        message = f"{data}.{timestamp}"
        sign = hmac.new(
            PROJECT_KEY.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        assert _verify_webhook_signature(data, timestamp, sign, PROJECT_KEY) is True

    def test_invalid_signature(self):
        assert (
            _verify_webhook_signature(
                '{"key": "value"}', 1700000000, "badsignature", PROJECT_KEY
            )
            is False
        )

    def test_different_key(self):
        data = '{"key": "value"}'
        timestamp = 1700000000
        message = f"{data}.{timestamp}"
        sign = hmac.new(
            PROJECT_KEY.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        assert _verify_webhook_signature(data, timestamp, sign, "wrong-key") is False


# --- Provider initialization tests ---


class TestProviderInit:
    def test_default_bsc_chain(self):
        provider = _make_provider()
        assert provider.chain_id == 56
        assert provider.token_address == "0x0000000000000000000000000000000000000000"
        assert provider._chain_decimals == 18

    def test_tron_chain(self):
        provider = _make_provider(chain_id=728126428)
        assert provider.chain_id == 728126428
        assert provider.token_address == "T9yD14Nj9j7xAB4dbGeiX9h8unkKHxuWwb"
        assert provider._chain_decimals == 6

    def test_custom_token_address(self):
        custom_token = "0xCustomToken"
        provider = _make_provider(token_address=custom_token)
        assert provider.token_address == custom_token

    def test_unsupported_chain_raises(self):
        with pytest.raises(ImproperlyConfigured, match="Unsupported chain_id"):
            _make_provider(chain_id=999)

    def test_no_preauth_raises(self):
        with pytest.raises(ImproperlyConfigured, match="pre-authorization"):
            _make_provider(capture=False)

    def test_custom_endpoint(self):
        provider = _make_provider(endpoint="https://test.paythefly.com")
        assert provider.pay_url == "https://test.paythefly.com/pay"

    def test_custom_deadline(self):
        provider = _make_provider(deadline_seconds=3600)
        assert provider.deadline_seconds == 3600


# --- get_form / redirect tests ---


class TestGetForm:
    @patch(
        "payments.paythefly._sign_typed_data",
        return_value="0xmockedsignature",
    )
    def test_redirects_to_payment_url(self, mock_sign):
        provider = _make_provider()
        payment = Payment()

        with pytest.raises(RedirectNeeded) as exc_info:
            provider.get_form(payment)

        redirect_url = str(exc_info.value)
        assert "pro.paythefly.com/pay" in redirect_url
        assert f"projectId={PROJECT_ID}" in redirect_url
        assert f"serialNo={PAYMENT_TOKEN}" in redirect_url
        assert "signature=" in redirect_url
        assert "chainId=56" in redirect_url
        assert "amount=0.01" in redirect_url

    @patch(
        "payments.paythefly._sign_typed_data",
        return_value="0xmockedsignature",
    )
    def test_changes_status_to_input(self, mock_sign):
        provider = _make_provider()
        payment = Payment()
        assert payment.status == PaymentStatus.WAITING

        with pytest.raises(RedirectNeeded):
            provider.get_form(payment)

        assert payment.status == PaymentStatus.INPUT

    @patch(
        "payments.paythefly._sign_typed_data",
        return_value="0xmockedsignature",
    )
    def test_stores_url_in_attrs(self, mock_sign):
        provider = _make_provider()
        payment = Payment()

        with pytest.raises(RedirectNeeded):
            provider.get_form(payment)

        assert "pro.paythefly.com/pay" in payment.attrs.paythefly_url
        assert isinstance(payment.attrs.paythefly_deadline, int)

    @patch(
        "payments.paythefly._sign_typed_data",
        return_value="0xmockedsignature",
    )
    def test_sign_called_with_correct_params(self, mock_sign):
        provider = _make_provider()
        payment = Payment()

        with pytest.raises(RedirectNeeded):
            provider.get_form(payment)

        mock_sign.assert_called_once()
        call_args = mock_sign.call_args
        assert call_args[0][0] == PRIVATE_KEY
        assert call_args[0][1] == 56
        assert call_args[0][2] == VERIFYING_CONTRACT
        msg = call_args[0][3]
        assert msg["projectId"] == PROJECT_ID
        assert msg["token"] == "0x0000000000000000000000000000000000000000"
        assert msg["amount"] == 10000000000000000  # 0.01 * 10^18
        assert msg["serialNo"] == PAYMENT_TOKEN


# --- Webhook processing tests ---


class TestProcessData:
    def test_valid_payment_webhook_confirmed(self):
        provider = _make_provider()
        payment = Payment()
        request = MagicMock()
        request.body = _make_webhook_body(payment, tx_type=1, confirmed=True)

        response = provider.process_data(payment, request)

        assert isinstance(response, HttpResponse)
        assert b"success" in response.content
        assert payment.status == PaymentStatus.CONFIRMED
        assert payment.transaction_id == "0xabc123def456"
        assert payment.captured_amount == payment.total

    def test_valid_payment_webhook_unconfirmed(self):
        provider = _make_provider()
        payment = Payment()
        request = MagicMock()
        request.body = _make_webhook_body(payment, tx_type=1, confirmed=False)

        response = provider.process_data(payment, request)

        assert isinstance(response, HttpResponse)
        assert b"success" in response.content
        # Should remain WAITING when not confirmed
        assert payment.status == PaymentStatus.WAITING
        assert payment.transaction_id == "0xabc123def456"

    def test_withdrawal_webhook(self):
        provider = _make_provider()
        payment = Payment()
        request = MagicMock()
        request.body = _make_webhook_body(payment, tx_type=2, confirmed=True)

        response = provider.process_data(payment, request)

        assert isinstance(response, HttpResponse)
        assert b"success" in response.content
        assert hasattr(payment.attrs, "paythefly_withdrawal")

    def test_invalid_json_body(self):
        provider = _make_provider()
        payment = Payment()
        request = MagicMock()
        request.body = b"not json"

        response = provider.process_data(payment, request)

        assert isinstance(response, HttpResponseBadRequest)

    def test_missing_required_fields(self):
        provider = _make_provider()
        payment = Payment()
        request = MagicMock()
        request.body = json.dumps({"data": "hello"}).encode()

        response = provider.process_data(payment, request)

        assert isinstance(response, HttpResponseBadRequest)

    def test_invalid_signature(self):
        provider = _make_provider()
        payment = Payment()
        data_str = json.dumps({"serial_no": payment.token, "tx_type": 1})
        body = json.dumps(
            {
                "data": data_str,
                "sign": "invalidsignature",
                "timestamp": int(time.time()),
            }
        )
        request = MagicMock()
        request.body = body.encode()

        response = provider.process_data(payment, request)

        assert isinstance(response, HttpResponseForbidden)

    def test_serial_no_mismatch(self):
        provider = _make_provider()
        payment = Payment()

        # Build webhook with wrong serial_no
        data_dict = {
            "serial_no": "wrong-serial",
            "tx_type": 1,
            "confirmed": True,
            "tx_hash": "0xabc",
        }
        data_str = json.dumps(data_dict)
        timestamp = int(time.time())
        message = f"{data_str}.{timestamp}"
        sign = hmac.new(
            PROJECT_KEY.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        body = json.dumps({"data": data_str, "sign": sign, "timestamp": timestamp})
        request = MagicMock()
        request.body = body.encode()

        response = provider.process_data(payment, request)

        assert isinstance(response, HttpResponseForbidden)


# --- Refund / Capture / Release tests ---


class TestUnsupportedOperations:
    def test_refund_raises_payment_error(self):
        provider = _make_provider()
        payment = Payment()
        with pytest.raises(PaymentError, match="dashboard"):
            provider.refund(payment)

    def test_capture_raises(self):
        provider = _make_provider()
        payment = Payment()
        with pytest.raises(NotImplementedError):
            provider.capture(payment)

    def test_release_raises(self):
        provider = _make_provider()
        payment = Payment()
        with pytest.raises(NotImplementedError):
            provider.release(payment)


# --- get_hidden_fields ---


class TestGetHiddenFields:
    def test_returns_empty_dict(self):
        provider = _make_provider()
        payment = Payment()
        assert provider.get_hidden_fields(payment) == {}


# --- EIP-712 signing integration test (requires eth_account) ---


class TestEIP712Signing:
    """Integration test for actual EIP-712 signing.

    Requires ``eth_account`` to be installed. Skipped if unavailable.
    """

    @pytest.fixture(autouse=True)
    def _check_eth_account(self):
        pytest.importorskip("eth_account")

    def test_sign_typed_data_returns_hex_string(self):
        from . import _sign_typed_data

        message = {
            "projectId": PROJECT_ID,
            "token": "0x0000000000000000000000000000000000000000",
            "amount": 10000000000000000,
            "serialNo": "ORDER001",
            "deadline": 1700000000,
        }
        signature = _sign_typed_data(
            PRIVATE_KEY,
            56,
            VERIFYING_CONTRACT,
            message,
        )
        assert isinstance(signature, str)
        assert len(signature) > 100  # A valid ECDSA sig is 130+ hex chars

    def test_sign_produces_consistent_output(self):
        from . import _sign_typed_data

        message = {
            "projectId": PROJECT_ID,
            "token": "0x0000000000000000000000000000000000000000",
            "amount": 10000000000000000,
            "serialNo": "ORDER001",
            "deadline": 1700000000,
        }
        sig1 = _sign_typed_data(PRIVATE_KEY, 56, VERIFYING_CONTRACT, message)
        sig2 = _sign_typed_data(PRIVATE_KEY, 56, VERIFYING_CONTRACT, message)
        assert sig1 == sig2
