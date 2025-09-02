from __future__ import annotations

import hashlib
from unittest.mock import MagicMock
from unittest.mock import Mock

import pytest
from django.http import HttpResponse
from django.http import HttpResponseForbidden

from payments import PaymentStatus

from . import DotpayProvider
from .forms import COMPLETED
from .forms import REJECTED

VARIANT = "dotpay"
PIN = "123"
PROCESS_POST = {
    "id": "123",
    "operation_number": "MI-5",
    "operation_type": "payment",
    "operation_status": COMPLETED,
    "operation_amount": "212.35",
    "operation_currency": "PLN",
    "operation_original_amount": "58.07",
    "operation_original_currency": "USD",
    "operation_datetime": "2018-02-28 12:00:00",
    "control": "1",
    "description": "Order #1",
    "email": "user@example.org",
    "p_info": "John Doe (seller@example.com)",
    "p_email": "seller@example.com",
    "channel": "1",
}


def get_post_with_sha256(post):
    post = post.copy()
    post["pin"] = PIN
    keys = [
        "pin",
        "id",
        "operation_number",
        "operation_type",
        "operation_status",
        "operation_amount",
        "operation_currency",
        "operation_original_amount",
        "operation_original_currency",
        "operation_datetime",
        "control",
        "description",
        "email",
        "p_info",
        "p_email",
        "channel",
    ]
    key = "".join([post[key] for key in keys])
    sha256 = hashlib.sha256()
    sha256.update(key.encode("utf-8"))
    post["signature"] = sha256.hexdigest()
    return post


class Payment(Mock):
    id = 1
    variant = VARIANT
    currency = "USD"
    total = 100
    status = PaymentStatus.WAITING

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


def test_get_hidden_fields(payment):
    provider = DotpayProvider(seller_id="123", pin=PIN)
    assert isinstance(provider.get_hidden_fields(payment), dict)


def test_process_data_payment_accepted(payment):
    request = MagicMock()
    request.POST = get_post_with_sha256(PROCESS_POST)
    provider = DotpayProvider(
        seller_id=123,
        pin=PIN,
        endpoint="test.endpoint.com",
        channel=1,
        lang="en",
        lock=True,
    )
    response = provider.process_data(payment, request)
    assert isinstance(response, HttpResponse)
    assert payment.status == PaymentStatus.CONFIRMED


def test_process_data_payment_rejected(payment):
    data = dict(PROCESS_POST)
    data.update({"operation_status": REJECTED})
    request = MagicMock()
    request.POST = get_post_with_sha256(data)
    provider = DotpayProvider(
        seller_id=123,
        pin=PIN,
        endpoint="test.endpoint.com",
        channel=1,
        lang="en",
        lock=True,
    )
    response = provider.process_data(payment, request)
    assert isinstance(response, HttpResponse)
    assert payment.status == PaymentStatus.REJECTED


def test_incorrect_process_data(payment):
    request = MagicMock()
    request.POST = PROCESS_POST  # no signature
    provider = DotpayProvider(seller_id="123", pin=PIN)
    response = provider.process_data(payment, request)
    assert isinstance(response, HttpResponseForbidden)


def test_uses_channel_groups_when_set(payment):
    channel_groups = "K,T"
    provider = DotpayProvider(
        seller_id=123,
        pin=PIN,
        endpoint="test.endpoint.com",
        channel=1,
        channel_groups=channel_groups,
        lang="en",
        lock=True,
    )
    hidden_fields = provider.get_hidden_fields(payment)
    assert hidden_fields["channel_groups"] == channel_groups
    assert hidden_fields.get("channel") is None
