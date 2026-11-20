from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from decimal import Decimal
from decimal import InvalidOperation
from urllib.parse import urlsplit
from uuid import UUID

import requests
from django.http import HttpResponse

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded
from payments.core import BasicProvider

CURRENCIES = frozenset({"USD", "EUR", "CNY", "RUB", "INR", "TRY", "KRW", "JPY"})
PENDING_STATUSES = (PaymentStatus.WAITING, PaymentStatus.INPUT)
CHECKOUT_ENDPOINT = "https://app.yolfi.com/api/checkout-sessions"


def _amount(value):
    """Canonical pricing-currency major units, never float or token units."""
    if not isinstance(value, (str, Decimal)) or len(str(value)) > 40:
        raise PaymentError("Invalid Yolfi pricing amount", code=409)
    try:
        amount = Decimal(value)
        # BasePayment.total has seven integer places and two decimal places.
        if not amount.is_finite() or not Decimal("0.01") <= amount < Decimal(10000000):
            raise ValueError
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError
    except (InvalidOperation, ValueError):
        raise PaymentError("Invalid Yolfi pricing amount", code=409) from None
    return format(amount, ".2f")


def _token(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise PaymentError("Invalid Yolfi payment reference", code=400) from None
    return value


def _url(value, *, hosted=False):
    if not isinstance(value, str) or any(ord(char) <= 32 for char in value):
        raise PaymentError("Invalid Yolfi checkout URL", code=409)
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in (("https",) if hosted else ("https", "http"))
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError
        # Access also rejects malformed ports, even though no server fetch occurs.
        _ = parsed.port
    except ValueError:
        raise PaymentError("Invalid Yolfi checkout URL", code=409) from None
    return value


class YolfiProvider(BasicProvider):
    """One-time native hosted checkout with signed final confirmation.

    Configure the native payment.confirmed webhook at the existing static
    provider callback URL. Browser redirects and COMPLETED checkout sessions
    are not payment evidence. Refunds, recurring payments and authorization-only
    flows are not supported.
    """

    def __init__(self, api_key, webhook_secret, capture=True):
        for value in (api_key, webhook_secret):
            if (
                not isinstance(value, str)
                or not value
                or len(value) > 8192
                or any(ord(char) <= 32 for char in value)
            ):
                raise ValueError("Yolfi requires a nonempty API key and webhook secret")
        if hmac.compare_digest(api_key.encode(), webhook_secret.encode()):
            raise ValueError("Use the webhook secret, not the API key, for signatures")
        if capture is not True:
            raise ValueError("Yolfi does not support authorization-only payments")
        super().__init__(capture=capture)
        self.api_key = api_key
        self.webhook_secret = webhook_secret

    def _pricing(self, payment):
        if not isinstance(payment.total, Decimal) or payment.currency not in CURRENCIES:
            raise PaymentError("Unsupported Yolfi pricing amount or currency", code=409)
        return _amount(payment.total), payment.currency, _token(str(payment.token))

    def _match_pricing(self, data, payment):
        amount, currency, reference = self._pricing(payment)
        if (
            not isinstance(data, dict)
            or _amount(data.get("amount")) != amount
            or data.get("currency") != currency
            or data.get("merchantOrderId") != reference
        ):
            raise PaymentError("Yolfi checkout pricing or reference mismatch", code=409)

    def _session(self, data, payment):
        self._match_pricing(data, payment)
        session_id = data.get("id")
        if (
            not isinstance(session_id, str)
            or not re.fullmatch(r"ycs_[A-Za-z0-9_-]{1,200}", session_id)
            or data.get("object") != "checkout_session"
            or data.get("status") not in ("OPEN", "PROCESSING", "COMPLETED")
            or data.get("paylinkId") is not None
        ):
            raise PaymentError("Invalid Yolfi checkout session", code=409)
        _url(data.get("url"), hosted=True)
        # Store only the immutable checkout contract needed for correlation.
        return {
            key: data[key]
            for key in (
                "id",
                "object",
                "status",
                "url",
                "amount",
                "currency",
                "merchantOrderId",
            )
        }

    def _request(self, payment):
        amount, currency, reference = self._pricing(payment)
        stored = getattr(payment.attrs, "yolfi_request", None)
        if stored is not None:
            self._match_pricing(stored, payment)
            return stored
        description = payment.description
        if not isinstance(description, str) or len(description) > 1000:
            raise PaymentError("Invalid Yolfi checkout description", code=400)
        payload = {
            "amount": amount,
            "currency": currency,
            "merchantOrderId": reference,
            "description": description,
            "successUrl": _url(payment.get_success_url()),
            "cancelUrl": _url(payment.get_failure_url()),
        }
        # Persist before HTTP: timeouts retry the identical body and key, even
        # if display text or return URLs have since changed.
        payment.attrs.yolfi_request = payload
        payment.save(update_fields=["extra_data"])
        return payload

    def get_form(self, payment, data=None):
        if payment.status not in PENDING_STATUSES:
            raise PaymentError("Yolfi checkout requires a pending payment", code=409)
        payload = self._request(payment)
        cached = getattr(payment.attrs, "yolfi_session", None)
        if cached is not None:
            session = self._session(cached, payment)
            if payment.transaction_id != session["id"]:
                raise PaymentError("Yolfi checkout session mismatch", code=409)
        else:
            if payment.transaction_id:
                raise PaymentError("Yolfi checkout session mismatch", code=409)
            headers = {
                "Idempotency-Key": (
                    f"django-payments-yolfi-{UUID(payload['merchantOrderId']).hex}"
                ),
                "Accept": "application/json",
            }
            headers["Authorization"] = f"Bearer {self.api_key}"
            try:
                response = requests.post(
                    CHECKOUT_ENDPOINT,
                    headers=headers,
                    json=payload,
                    timeout=10,
                    allow_redirects=False,
                )
            except requests.RequestException:
                raise PaymentError(
                    "Yolfi checkout request failed; retry the same payment"
                ) from None
            if not 200 <= response.status_code < 300:
                raise PaymentError("Yolfi checkout request was not accepted")
            try:
                result = response.json()
            except ValueError:
                raise PaymentError("Invalid Yolfi checkout response") from None
            if (
                not isinstance(result, dict)
                or result.get("success") is not True
                or not isinstance(result.get("data"), dict)
            ):
                raise PaymentError("Invalid Yolfi response", code=502)
            session = self._session(result["data"], payment)
            payment.transaction_id = session["id"]
            payment.attrs.yolfi_session = session
            payment.save(update_fields=["transaction_id", "extra_data"])
        raise RedirectNeeded(session["url"])

    def _event(self, request):
        if request.method != "POST":
            raise PaymentError("Yolfi webhooks require POST", code=405)
        body = request.body
        signature = request.headers.get("X-Yolfi-Signature")
        if (
            not isinstance(body, bytes)
            or len(body) > 1048576
            or not isinstance(signature, str)
            or len(signature) > 128
        ):
            raise PaymentError("Invalid Yolfi signature", code=400)
        try:
            received = base64.b64decode(signature, validate=True)
        except ValueError:
            raise PaymentError("Invalid Yolfi signature", code=400) from None
        expected = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(received, expected):
            raise PaymentError("Invalid Yolfi signature", code=400)
        try:
            event = json.loads(body)
        except (ValueError, UnicodeError):
            raise PaymentError("Invalid Yolfi webhook payload", code=400) from None
        if (
            not isinstance(event, dict)
            or not isinstance(event.get("data"), dict)
            or not isinstance(event.get("id"), str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", event["id"])
            or not isinstance(event.get("type"), str)
            or not 1 <= len(event["type"]) <= 100
        ):
            raise PaymentError("Invalid Yolfi webhook payload", code=400)
        # This header is not signed and must never override the body identity.
        event_header = request.headers.get("X-Yolfi-Event-ID")
        if event_header is not None and event_header != event["id"]:
            raise PaymentError("Yolfi event identity mismatch", code=400)
        _token(event["data"].get("merchantOrderId"))
        return event

    def get_token_from_request(self, payment, request):
        return self._event(request)["data"]["merchantOrderId"]

    def process_data(self, payment, request):
        try:
            event = self._event(request)
            data = event["data"]
            session = self._session(
                getattr(payment.attrs, "yolfi_session", None), payment
            )
            self._match_pricing(getattr(payment.attrs, "yolfi_request", None), payment)
            if (
                payment.transaction_id != session["id"]
                or data.get("checkoutSessionId") != session["id"]
                or data.get("merchantOrderId") != str(payment.token)
                or data.get("currency") != session["currency"]
            ):
                raise PaymentError(
                    "Yolfi payment reference or currency mismatch", code=409
                )
            if event["type"] != "payment.confirmed":
                return HttpResponse("OK")
            if (
                data.get("status") != "confirmed"
                or data.get("paymentType") != "ONE_TIME"
                or data.get("subscriptionId") is not None
                or data.get("paylinkId") is not None
            ):
                raise PaymentError("Unsupported Yolfi payment confirmation", code=400)
            invoice_id = _token(data.get("invoiceId"))
            previous = getattr(payment.attrs, "yolfi_confirmation", None)
            if previous is not None and (
                not isinstance(previous, dict)
                or previous.get("invoice_id") != invoice_id
            ):
                raise PaymentError("Yolfi invoice mismatch", code=409)
            # The built-in callback view locks this payment row in an atomic
            # transaction. Replays cannot emit a second confirmation signal.
            if payment.status in PENDING_STATUSES:
                payment.attrs.yolfi_confirmation = {
                    "event_id": event["id"],
                    "invoice_id": invoice_id,
                }
                # Native event.amount is a token amount; amountUsd is USD even
                # when pricing uses EUR. Capture the bound local pricing total.
                payment.captured_amount = payment.total
                payment.save(update_fields=["captured_amount", "extra_data"])
                payment.change_status(PaymentStatus.CONFIRMED)
            return HttpResponse("OK")
        except PaymentError as error:
            return HttpResponse(str(error), status=error.code or 400)
