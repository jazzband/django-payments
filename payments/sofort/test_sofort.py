from __future__ import annotations

import json
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from payments import PaymentStatus
from payments import RedirectNeeded

from . import SofortProvider

SECRET = "abcd1234"
CLIENT_ID = "1234"
PROJECT_ID = "abcd"


class Payment(Mock):
    id = 1
    variant = "sagepay"
    currency = "USD"
    total = 100
    status = PaymentStatus.WAITING
    transaction_id = None
    captured_amount = 0
    billing_first_name = "John"
    description = "foo bar"

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
    return SofortProvider(id=CLIENT_ID, project_id=PROJECT_ID, key=SECRET)


@patch("xmltodict.parse")
@patch("requests.post")
def test_provider_raises_redirect_needed_on_success(
    mocked_post, mocked_parser, payment, provider
):
    response = MagicMock()
    response.status_code = 200
    mocked_post.return_value = response
    mocked_parser.return_value = {
        "new_transaction": {"payment_url": "http://payment.com"}
    }
    with pytest.raises(RedirectNeeded):
        provider.get_form(payment)


@patch("xmltodict.parse")
@patch("requests.post")
@patch("payments.sofort.redirect")
def test_provider_redirects_on_success(
    mocked_redirect, mocked_post, mocked_parser, payment, provider
):
    transaction_id = "1234"
    request = MagicMock()
    request.GET = {"trans": transaction_id}
    mocked_parser.return_value = {
        "transactions": {
            "transaction_details": {
                "status": "ok",
                "sender": {"holder": "John Doe", "country_code": "EN"},
            }
        }
    }
    provider.process_data(payment, request)
    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.captured_amount == payment.total
    assert payment.transaction_id == transaction_id


@patch("xmltodict.parse")
@patch("requests.post")
@patch("payments.sofort.redirect")
def test_provider_redirects_on_failure(
    mocked_redirect, mocked_post, mocked_parser, payment, provider
):
    transaction_id = "1234"
    request = MagicMock()
    request.GET = {"trans": transaction_id}
    mocked_parser.return_value = {}
    provider.process_data(payment, request)
    assert payment.status == PaymentStatus.REJECTED
    assert payment.captured_amount == 0
    assert payment.transaction_id == transaction_id


@patch("xmltodict.parse")
@patch("requests.post")
def test_provider_refunds_payment(mocked_post, mocked_parser, payment, provider):
    payment.extra_data = json.dumps(
        {
            "transactions": {
                "transaction_details": {
                    "status": "ok",
                    "sender": {
                        "holder": "John Doe",
                        "country_code": "EN",
                        "bic": "1234",
                        "iban": "abcd",
                    },
                }
            }
        }
    )
    mocked_parser.return_value = {}
    provider.refund(payment)
    assert payment.status == PaymentStatus.REFUNDED
