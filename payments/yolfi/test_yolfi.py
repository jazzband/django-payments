from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch

import pytest
import requests
from django.http import Http404

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded
from payments import yolfi
from payments.core import BasicProvider
from payments.models import PaymentAttributeProxy

# All credentials, HTTP responses and identifiers below are synthetic fixtures.
YOLFI_API_KEY = "EXAMPLE_API_KEY"
YOLFI_WEBHOOK_SECRET = "EXAMPLE_WEBHOOK_SECRET"
TOKEN = "00000000-0000-4000-8000-000000000001"
INVOICE = "00000000-0000-4000-8000-000000000002"
SESSION = "ycs_test_checkout"
EVENT = "evt_00000000-0000-4000-8000-000000000003"
CHECKOUT_URL = f"https://yolfi.com/{SESSION}"


class Payment:
    """Explicit model collaborator; real JSON attrs proxy, no database."""

    def __init__(self):
        self.token = TOKEN
        self.variant = "yolfi"
        self.total = Decimal("19.95")
        self.currency = "EUR"
        self.description = "Test order"
        self.status = PaymentStatus.WAITING
        self.captured_amount = Decimal(0)
        self.transaction_id = ""
        self.extra_data = ""
        self.status_changes = []
        self.saved = {}
        self.saves = []

    @property
    def attrs(self):
        return PaymentAttributeProxy(self)

    def save(self, **kwargs):
        fields = kwargs.get(
            "update_fields",
            [
                "token",
                "transaction_id",
                "extra_data",
                "captured_amount",
                "status",
            ],
        )
        self.saves.append(list(fields))
        for field in fields:
            self.saved[field] = copy.deepcopy(getattr(self, field))

    def change_status(self, status):
        self.status = status
        self.status_changes.append(status)
        self.save(update_fields=["status"])

    def get_success_url(self):
        return "https://example.com/success"

    def get_failure_url(self):
        return "https://example.com/cancel"

    def reload(self):
        payment = Payment()
        for field, value in self.saved.items():
            setattr(payment, field, copy.deepcopy(value))
        payment.saved = copy.deepcopy(self.saved)
        return payment


def session_fixture(**overrides):
    value = {
        "id": SESSION,
        "object": "checkout_session",
        "status": "OPEN",
        "url": CHECKOUT_URL,
        "amount": "19.95",
        "currency": "EUR",
        "merchantOrderId": TOKEN,
    }
    value.update(overrides)
    return value


def event_fixture(**overrides):
    value = {
        "id": EVENT,
        "type": "payment.confirmed",
        "created": 1700000000,
        "livemode": False,
        "data": {
            "checkoutSessionId": SESSION,
            "merchantOrderId": TOKEN,
            "invoiceId": INVOICE,
            "paymentType": "ONE_TIME",
            "status": "confirmed",
            "currency": "EUR",
            # Token receivables and USD equivalents are NOT the EUR order total.
            "amount": "0.008",
            "amountUsd": "21.32",
            "rate": "2493.75",
        },
    }
    value.update(overrides)
    return value


def signed_request(
    event=None,
    raw=None,
    secret=YOLFI_WEBHOOK_SECRET,
):
    body = (
        raw
        if raw is not None
        else json.dumps(
            event if event is not None else event_fixture(),
            ensure_ascii=False,
        ).encode()
    )
    signature = base64.b64encode(
        hmac.new(
            secret.encode(),
            body,
            hashlib.sha256,
        ).digest()
    ).decode()
    return SimpleNamespace(
        method="POST", body=body, headers={"X-Yolfi-Signature": signature}
    )


class YolfiProviderTests(TestCase):
    def setUp(self):
        assert hasattr(yolfi, "YolfiProvider"), "Native Yolfi provider missing"
        self.provider = yolfi.YolfiProvider(
            api_key=YOLFI_API_KEY,
            webhook_secret=YOLFI_WEBHOOK_SECRET,
        )
        self.payment = Payment()
        self.http = patch("payments.yolfi.requests.post").start()
        self.addCleanup(patch.stopall)
        self.http.return_value = Mock(status_code=201)
        self.http.return_value.json.return_value = {
            "success": True,
            "data": session_fixture(),
        }

    def create_checkout(self, payment=None):
        with pytest.raises(RedirectNeeded) as result:
            self.provider.get_form(payment or self.payment)
        assert str(result.value) == CHECKOUT_URL

    def confirm(self, request=None, payment=None):
        return self.provider.process_data(
            payment or self.payment, request or signed_request()
        )

    def test_checkout_native_contract_and_snapshot(self):
        assert isinstance(self.provider, BasicProvider)
        self.create_checkout()
        args, kwargs = self.http.call_args
        assert args == ("https://app.yolfi.com/api/checkout-sessions",)
        assert kwargs["json"] == {
            "amount": "19.95",
            "currency": "EUR",
            "merchantOrderId": TOKEN,
            "description": "Test order",
            "successUrl": "https://example.com/success",
            "cancelUrl": "https://example.com/cancel",
        }
        assert kwargs["headers"]["Authorization"] == f"Bearer {YOLFI_API_KEY}"
        key = kwargs["headers"]["Idempotency-Key"]
        assert 16 <= len(key) <= 200
        assert kwargs["timeout"] == 10
        assert kwargs["allow_redirects"] is False
        assert self.payment.transaction_id == SESSION
        assert self.payment.saved["transaction_id"] == SESSION
        assert self.payment.status == PaymentStatus.WAITING
        assert self.payment.status_changes == []
        attrs = json.loads(self.payment.saved["extra_data"])
        assert attrs["yolfi_session"]["amount"] == "19.95"
        assert "customer" not in attrs["yolfi_session"]
        assert YOLFI_API_KEY not in self.payment.extra_data

    def test_cached_session_survives_json_round_trip(self):
        self.create_checkout()
        payment = self.payment.reload()
        self.create_checkout(payment)
        assert self.http.call_count == 1

    def test_timeout_retries_identical_immutable_request(self):
        self.http.side_effect = requests.Timeout("synthetic fixture timeout")
        with pytest.raises(PaymentError):
            self.provider.get_form(self.payment)
        first_call = (
            self.http.call_args.args,
            copy.deepcopy(self.http.call_args.kwargs),
        )
        payment = self.payment.reload()
        payment.description = "Changed display text after timeout"
        payment.get_success_url = lambda: "https://example.com/other"
        self.http.side_effect = None
        self.create_checkout(payment)
        assert (self.http.call_args.args, self.http.call_args.kwargs) == first_call

    def test_changed_total_after_timeout_cannot_reuse_key(self):
        self.http.side_effect = requests.Timeout()
        with pytest.raises(PaymentError):
            self.provider.get_form(self.payment)
        self.payment.total = Decimal("20.00")
        with pytest.raises(PaymentError):
            self.provider.get_form(self.payment)
        assert self.http.call_count == 1

    def test_changed_currency_or_total_after_checkout_rejected(self):
        self.create_checkout()
        for field, value in [("total", Decimal("0.01")), ("currency", "USD")]:
            payment = self.payment.reload()
            setattr(payment, field, value)
            with self.subTest(field=field), pytest.raises(PaymentError):
                self.provider.get_form(payment)
        assert self.http.call_count == 1

    def test_all_supported_currencies_remain_major_units(self):
        for currency in ["USD", "EUR", "CNY", "RUB", "INR", "TRY", "KRW", "JPY"]:
            with self.subTest(currency=currency):
                payment = Payment()
                payment.total = Decimal("0.01")
                payment.currency = currency
                self.http.return_value.json.return_value = {
                    "success": True,
                    "data": session_fixture(amount="0.01", currency=currency),
                }
                self.create_checkout(payment)
                assert self.http.call_args.kwargs["json"]["amount"] == "0.01"

    def test_invalid_totals_currencies_and_references_fail_before_http(self):
        for field, values in {
            "total": [
                Decimal(0),
                Decimal(-1),
                Decimal("NaN"),
                Decimal("Infinity"),
                Decimal("0.001"),
                "invalid",
                19.95,
                Decimal(10000000),
            ],
            "currency": ["BTC", "eur", "", None],
            "token": ["", "not-a-uuid", "x" * 256],
            "description": ["x" * 1001, None],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    payment = Payment()
                    setattr(payment, field, value)
                    with pytest.raises(PaymentError):
                        self.provider.get_form(payment)
        self.http.assert_not_called()

    def test_terminal_payment_does_not_start_checkout(self):
        for status in [
            PaymentStatus.CONFIRMED,
            PaymentStatus.CANCELLED,
            PaymentStatus.REJECTED,
            PaymentStatus.REFUNDED,
            PaymentStatus.ERROR,
            PaymentStatus.PREAUTH,
        ]:
            self.payment.status = status
            with self.subTest(status=status), pytest.raises(PaymentError):
                self.provider.get_form(self.payment)
        self.http.assert_not_called()

    def test_malformed_configuration_and_preauthorization_rejected(self):
        for key, value in [
            ("api_key", ""),
            ("api_key", None),
            ("api_key", YOLFI_API_KEY + "\n"),
            ("webhook_secret", ""),
            ("webhook_secret", None),
            ("webhook_secret", YOLFI_API_KEY),
            ("capture", False),
        ]:
            kwargs = {
                "api_key": YOLFI_API_KEY,
                "webhook_secret": YOLFI_WEBHOOK_SECRET,
            }
            kwargs[key] = value
            with (
                self.subTest(key=key, value=value),
                pytest.raises(ValueError, match=r"Yolfi|webhook|preauthorization"),
            ):
                yolfi.YolfiProvider(**kwargs)

    def test_unsupported_operations_remain_explicit(self):
        for name in ["refund", "capture", "release", "cancel"]:
            with self.subTest(name=name), pytest.raises(NotImplementedError):
                getattr(self.provider, name)(self.payment)

    def test_http_errors_never_expose_provider_body_or_credentials(self):
        for status in [301, 400, 401, 409, 422, 429, 500, 503]:
            self.payment = Payment()
            self.http.return_value.status_code = status
            self.http.return_value.text = YOLFI_API_KEY + YOLFI_WEBHOOK_SECRET
            with self.subTest(status=status), pytest.raises(PaymentError) as error:
                self.provider.get_form(self.payment)
            assert YOLFI_API_KEY not in str(error.value)
            assert YOLFI_WEBHOOK_SECRET not in str(error.value)
            assert self.payment.status_changes == []
            assert self.payment.transaction_id == ""

    def test_network_errors_are_sanitized_and_retryable(self):
        for error in [
            requests.Timeout(YOLFI_API_KEY),
            requests.ConnectionError(YOLFI_WEBHOOK_SECRET),
        ]:
            self.http.side_effect = error
            with (
                self.subTest(error=type(error).__name__),
                pytest.raises(PaymentError) as result,
            ):
                self.provider.get_form(self.payment)
            assert YOLFI_API_KEY not in str(result.value)
            assert YOLFI_WEBHOOK_SECRET not in str(result.value)

    def test_invalid_json_and_non_object_session_rejected(self):
        for result in [None, [], "invalid"]:
            self.payment = Payment()
            self.http.return_value.json.return_value = result
            with self.subTest(result=result), pytest.raises(PaymentError):
                self.provider.get_form(self.payment)
        self.http.return_value.json.side_effect = ValueError("fixture invalid JSON")
        with pytest.raises(PaymentError):
            self.provider.get_form(Payment())

    def test_malformed_or_mismatched_session_cannot_redirect(self):
        cases = [
            {"id": "not-a-session"},
            {"id": None},
            {"url": "http://example.com"},
            {"url": "javascript:alert(1)"},
            {"url": "https://user@example.com"},
            {"url": "https://example.com/\n"},
            {"amount": "19.94"},
            {"amount": "NaN"},
            {"currency": "USD"},
            {"merchantOrderId": "other-order"},
            {"status": "EXPIRED"},
            {"status": "unknown"},
            {"status": []},
            {"object": "paylink"},
            {"paylinkId": "test-link"},
        ]
        for overrides in cases:
            self.http.return_value.json.return_value = {
                "success": True,
                "data": session_fixture(**overrides),
            }
            with self.subTest(overrides=overrides), pytest.raises(PaymentError):
                self.provider.get_form(Payment())

    def test_completed_checkout_is_not_payment_confirmation(self):
        self.http.return_value.json.return_value = {
            "success": True,
            "data": session_fixture(status="COMPLETED"),
        }
        self.create_checkout()
        assert self.payment.status == PaymentStatus.WAITING
        assert self.payment.captured_amount == Decimal(0)

    def test_signature_routes_native_direct_data(self):
        request = signed_request()
        assert self.provider.get_token_from_request(None, request) == TOKEN
        self.http.assert_not_called()

    def test_raw_body_unicode_and_whitespace_signature(self):
        self.create_checkout()
        event = event_fixture()
        event["data"]["metadata"] = {"test": "สวัสดี"}
        raw = json.dumps(event, ensure_ascii=False, indent=2).encode()
        request = signed_request(raw=raw)
        assert self.confirm(request).status_code == 200
        assert self.payment.status == PaymentStatus.CONFIRMED

    def test_invalid_signature_never_routes_or_mutates(self):
        self.create_checkout()
        for signature in [
            None,
            "",
            "not base64!",
            "00" * 32,
            "t=1700000000,v1=fixture",
            base64.b64encode(b"short").decode(),
        ]:
            request = signed_request()
            request.headers["X-Yolfi-Signature"] = signature
            with self.subTest(signature=signature), pytest.raises(PaymentError):
                self.provider.get_token_from_request(None, request)
            assert self.confirm(request).status_code == 400
        assert self.payment.status_changes == []

    def test_tampered_bytes_and_wrong_secret_rejected(self):
        self.create_checkout()
        requests_to_test = [
            signed_request(
                secret=YOLFI_API_KEY,
            ),
            signed_request(
                secret="EXAMPLE_WRONG_SECRET",
            ),
        ]
        for suffix in [b" ", b"x"]:
            request = signed_request()
            request.body += suffix
            requests_to_test.append(request)
        for request in requests_to_test:
            with pytest.raises(PaymentError):
                self.provider.get_token_from_request(None, request)
            assert self.confirm(request).status_code == 400
        assert self.payment.status_changes == []

    def test_signed_malformed_payloads_fail_closed(self):
        self.create_checkout()
        for raw in [b"{", b"[]", b"null", b"42", b"\xff"]:
            request = signed_request(raw=raw)
            with self.subTest(raw=raw), pytest.raises(PaymentError):
                self.provider.get_token_from_request(None, request)
            assert self.confirm(request).status_code == 400
        for changes in [
            {"id": ""},
            {"id": None},
            {"data": []},
            {"type": ""},
            {"type": None},
            {"data": {}},
        ]:
            request = signed_request(event_fixture(**changes))
            with self.subTest(changes=changes), pytest.raises(PaymentError):
                self.provider.get_token_from_request(None, request)
        assert self.payment.status_changes == []

    def test_unsigned_header_cannot_replace_signed_event_identity(self):
        self.create_checkout()
        request = signed_request()
        request.headers["X-Yolfi-Event-ID"] = "evt_other"
        assert self.confirm(request).status_code == 400
        assert self.payment.status_changes == []

    def test_money_and_reference_mismatches_cannot_confirm(self):
        self.create_checkout()
        cases = [
            {"checkoutSessionId": "ycs_other"},
            {"merchantOrderId": "00000000-0000-4000-8000-000000000099"},
            {"merchantOrderId": None},
            {"currency": "USD"},
            {"invoiceId": ""},
            {"invoiceId": "not-a-uuid"},
            {"paymentType": "RECURRING"},
            {"subscriptionId": "test-subscription"},
            {"paylinkId": "test-paylink"},
            {"status": "pending"},
        ]
        for changes in cases:
            event = event_fixture()
            event["data"].update(changes)
            with self.subTest(changes=changes):
                assert self.confirm(signed_request(event)).status_code in [400, 409]
        assert self.payment.status_changes == []
        assert self.payment.captured_amount == Decimal(0)

    def test_missing_local_snapshot_or_transaction_binding_fails_closed(self):
        assert self.confirm().status_code in [400, 409]
        self.create_checkout()
        self.payment.transaction_id = "ycs_other"
        assert self.confirm().status_code == 409
        assert self.payment.status_changes == []

    def test_local_snapshot_or_payment_drift_fails_closed(self):
        self.create_checkout()
        for changes in [
            {"amount": "1.00"},
            {"currency": "USD"},
            {"merchantOrderId": "other-order"},
        ]:
            payment = self.payment.reload()
            snapshot = payment.attrs.yolfi_session
            snapshot.update(changes)
            payment.attrs.yolfi_session = snapshot
            with self.subTest(changes=changes):
                assert self.confirm(payment=payment).status_code == 409
        payment = self.payment.reload()
        payment.total = Decimal("1.00")
        assert self.confirm(payment=payment).status_code == 409

    def test_confirm_sets_pricing_total_not_token_or_usd_receivable(self):
        self.create_checkout()
        assert self.confirm().status_code == 200
        assert self.payment.captured_amount == Decimal("19.95")
        assert self.payment.status_changes == [PaymentStatus.CONFIRMED]
        restored = self.payment.reload()
        assert restored.captured_amount == Decimal("19.95")
        assert restored.status == PaymentStatus.CONFIRMED
        assert (restored.attrs.yolfi_confirmation) == (
            {"event_id": EVENT, "invoice_id": INVOICE}
        )
        assert "amountUsd" not in restored.extra_data

    def test_confirmation_replay_does_not_repeat_status_signal(self):
        self.create_checkout()
        self.confirm()
        self.confirm()
        other = event_fixture(id="evt_other_confirmation")
        self.confirm(signed_request(other))
        assert self.payment.status_changes == [PaymentStatus.CONFIRMED]
        restored = self.payment.reload()
        assert self.confirm(payment=restored).status_code == 200
        assert restored.status_changes == []
        assert restored.captured_amount == Decimal("19.95")

    def test_different_invoice_replay_rejected(self):
        self.create_checkout()
        self.confirm()
        event = event_fixture()
        event["data"]["invoiceId"] = "00000000-0000-4000-8000-000000000099"
        assert self.confirm(signed_request(event)).status_code == 409
        assert self.payment.status_changes == [PaymentStatus.CONFIRMED]

    def test_terminal_states_never_revived(self):
        self.create_checkout()
        for status in [
            PaymentStatus.REFUNDED,
            PaymentStatus.CANCELLED,
            PaymentStatus.REJECTED,
            PaymentStatus.ERROR,
            PaymentStatus.PREAUTH,
        ]:
            payment = self.payment.reload()
            payment.status = status
            assert self.confirm(payment=payment).status_code == 200
            assert payment.status == status
            assert payment.status_changes == []

    def test_correlated_irrelevant_events_and_late_expiry_do_not_mutate(self):
        self.create_checkout()
        for event_type in [
            "invoice.created",
            "invoice.overdue",
            "subscription.cancelled",
        ]:
            event = event_fixture(type=event_type)
            event["data"]["status"] = "expired"
            assert self.confirm(signed_request(event)).status_code == 200
        assert self.payment.status_changes == []
        self.confirm()
        event = event_fixture(type="invoice.overdue")
        assert self.confirm(signed_request(event)).status_code == 200
        assert self.payment.status_changes == [PaymentStatus.CONFIRMED]

    def test_browser_return_and_cancel_never_confirm(self):
        self.create_checkout()
        request = signed_request()
        request.method = "GET"
        assert self.confirm(request).status_code == 405
        assert self.payment.status_changes == []

    def test_cached_provider_does_not_share_payment_data(self):
        self.create_checkout()
        other = Payment()
        other.token = "00000000-0000-4000-8000-000000000099"
        other.total = Decimal("20.00")
        self.http.return_value.json.return_value = {
            "success": True,
            "data": session_fixture(
                id="ycs_other", merchantOrderId=other.token, amount="20.00"
            ),
        }
        with pytest.raises(RedirectNeeded):
            self.provider.get_form(other)
        assert other.transaction_id != self.payment.transaction_id
        assert self.confirm().status_code == 200
        assert other.status == PaymentStatus.WAITING

    def test_static_callback_uses_authenticated_token_and_existing_row_lock(self):
        from payments import urls

        self.create_checkout()
        manager = Mock()
        model = SimpleNamespace(_default_manager=manager)
        with (
            patch.object(urls, "provider_factory", return_value=self.provider),
            patch.object(urls, "get_payment_model", return_value=model),
            patch.object(
                urls, "get_object_or_404", return_value=self.payment
            ) as lookup,
        ):
            response = urls.static_callback(signed_request(), "yolfi")
            assert response.status_code == 200
            manager.select_for_update.assert_called_once_with()
            lookup.assert_called_once_with(
                manager.select_for_update.return_value, token=TOKEN
            )
        assert self.payment.status_changes == [PaymentStatus.CONFIRMED]

    def test_static_callback_invalid_signature_and_unknown_token_errors(self):
        from payments import urls

        with patch.object(urls, "provider_factory", return_value=self.provider):
            request = signed_request(secret="EXAMPLE_WRONG_SECRET")
            response = urls.static_callback(request, "yolfi")
            assert response.status_code == 400
            with (
                patch.object(urls, "get_payment_model", return_value=Mock()),
                patch.object(urls, "get_object_or_404", side_effect=Http404),
            ):
                response = urls.static_callback(signed_request(), "yolfi")
                assert response.status_code == 404
                assert TOKEN.encode() not in response.content

    def test_documented_success_data_envelope_can_redirect(self):
        self.http.return_value.json.return_value = {
            "success": True,
            "data": session_fixture(),
        }
        try:
            self.create_checkout()
        except PaymentError as error:
            pytest.fail("Documented success/data envelope rejected: " + str(error))

    def test_invalid_official_envelopes_cannot_redirect(self):
        for value in [
            {"success": False, "data": session_fixture()},
            {"success": 1, "data": session_fixture()},
            {"success": True, "data": []},
            {"success": True},
            session_fixture(),
        ]:
            self.http.return_value.json.return_value = value
            with self.subTest(value=value), pytest.raises(PaymentError):
                self.provider.get_form(Payment())

    def test_malformed_ports_rejected_before_checkout_or_redirect(self):
        for port in ["invalid", "65536", "-1"]:
            url = f"https://example.com:{port}/checkout"
            for method in ["get_success_url", "get_failure_url"]:
                payment = Payment()
                with self.subTest(port=port, method=method):
                    with (
                        patch.object(payment, method, return_value=url),
                        pytest.raises(PaymentError) as error,
                    ):
                        self.provider.get_form(payment)
                    assert error.value.code == 409
                    self.http.assert_not_called()
                    assert payment.saves == []
                    assert payment.status_changes == []
            payment = Payment()
            self.http.return_value.json.return_value = {
                "success": True,
                "data": session_fixture(url=url),
            }
            with self.subTest(port=port, method="hosted"):
                with pytest.raises(PaymentError) as error:
                    self.provider.get_form(payment)
                assert error.value.code == 409
                assert payment.transaction_id == ""
                assert payment.status_changes == []
            self.http.reset_mock()
        url = "https://example.com:443/checkout"
        assert yolfi._url(url) == url
        assert yolfi._url(url, hosted=True) == url
