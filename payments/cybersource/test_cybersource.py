from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from django.core import signing

from payments import PaymentStatus
from payments import PurchasedItem
from payments import RedirectNeeded

from . import ACCEPTED
from . import AUTHENTICATE_REQUIRED
from . import TRANSACTION_SETTLED
from . import CyberSourceProvider

MERCHANT_ID = "abcd1234"
PASSWORD = "1234abdd1234abcd"
ORG_ID = "abc"

PROCESS_DATA = {
    "name": "John Doe",
    "number": "371449635398431",
    "expiration_0": "5",
    "expiration_1": date.today().year + 1,
    "cvv2": "1234",
    "fingerprint": "abcd1234",
}


class Payment(Mock):
    id = 1
    variant = "cybersource"
    currency = "USD"
    total = 100
    status = PaymentStatus.WAITING
    transaction_id = None
    captured_amount = 0
    message = ""

    class attrs:
        fingerprint_session_id = "fake"
        merchant_defined_data: dict[str, str] = {}

    def get_process_url(self):
        return "http://example.com"

    def get_failure_url(self):
        return "http://cancel.com"

    def get_success_url(self):
        return "http://success.com"

    def change_status(self, status, message=""):
        self.status = status
        self.message = message

    def get_purchased_items(self):
        return [
            PurchasedItem(
                name="foo",
                quantity=Decimal("10"),
                price=Decimal("20"),
                currency="USD",
                sku="bar",
            )
        ]


@pytest.fixture
@patch("payments.cybersource.suds.client.Client", new=MagicMock())
def provider():
    payment = Payment()
    return payment, CyberSourceProvider(
        merchant_id=MERCHANT_ID, password=PASSWORD, org_id=ORG_ID
    )


@patch.object(CyberSourceProvider, "_make_request")
def test_provider_raises_redirect_needed_on_success(mocked_request, provider):
    payment, prov = provider
    transaction_id = 1234
    response = MagicMock()
    response.requestID = transaction_id
    response.reasonCode = 100
    mocked_request.return_value = response
    with pytest.raises(RedirectNeeded):
        prov.get_form(payment=payment, data=PROCESS_DATA)
    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.captured_amount == payment.total
    assert payment.transaction_id == transaction_id


@patch.object(CyberSourceProvider, "_make_request")
def test_provider_returns_form_on_3d_secure(mocked_request, provider):
    payment, prov = provider
    response = MagicMock()
    response.reasonCode = AUTHENTICATE_REQUIRED
    mocked_request.return_value = response
    form = prov.get_form(payment=payment, data=PROCESS_DATA)
    assert payment.status == PaymentStatus.WAITING
    assert "PaReq" in form.fields


@patch.object(CyberSourceProvider, "_make_request")
def test_provider_shows_validation_error_message_response(mocked_request, provider):
    payment, prov = provider
    error_message = "The card you are trying to use was reported as lost or stolen."
    error_code = 205
    response = MagicMock()
    response.reasonCode = error_code
    mocked_request.return_value = response
    form = prov.get_form(payment=payment, data=PROCESS_DATA)
    assert form.errors["__all__"][0] == error_message


def test_provider_shows_validation_error_message_duplicate(provider):
    payment, prov = provider
    payment.transaction_id = 1
    error_message = "This payment has already been processed."
    form = prov.get_form(payment=payment, data=PROCESS_DATA)
    assert form.errors["__all__"][0] == error_message


@patch.object(CyberSourceProvider, "_make_request")
def test_provider_captures_payment(mocked_request, provider):
    payment, prov = provider
    transaction_id = 1234
    response = MagicMock()
    response.requestID = transaction_id
    response.reasonCode = TRANSACTION_SETTLED
    mocked_request.return_value = response
    prov.capture(payment)
    assert payment.status == PaymentStatus.CONFIRMED


@patch.object(CyberSourceProvider, "_make_request")
def test_provider_refunds_payment(mocked_request, provider):
    payment, prov = provider
    payment.captured_amount = payment.total
    response = MagicMock()
    response.reasonCode = ACCEPTED
    mocked_request.return_value = response
    amount = prov.refund(payment)
    assert payment.total == amount


@patch.object(CyberSourceProvider, "_make_request")
def test_provider_releases_payment(mocked_request, provider):
    payment, prov = provider
    transaction_id = 123
    response = MagicMock()
    response.requestID = transaction_id
    response.reasonCode = ACCEPTED
    mocked_request.return_value = response
    prov.release(payment)
    assert payment.transaction_id == transaction_id


@patch("payments.cybersource.redirect")
@patch.object(CyberSourceProvider, "_make_request")
def test_provider_redirects_on_success_captured_payment(
    mocked_request, mocked_redirect, provider
):
    payment, prov = provider
    transaction_id = 1234
    xid = "abc"
    payment.attrs.xid = xid

    response = MagicMock()
    response.requestID = transaction_id
    response.reasonCode = ACCEPTED
    mocked_request.return_value = response

    request = MagicMock()
    request.POST = {"MD": xid}
    request.GET = {
        "token": signing.dumps(
            {
                "expiration": {"year": 2023, "month": 9},
                "name": "John Doe",
                "number": "371449635398431",
                "cvv2": "123",
            }
        )
    }
    prov.process_data(payment, request)
    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.captured_amount == payment.total
    assert payment.transaction_id == transaction_id


@patch("payments.cybersource.redirect")
@patch.object(CyberSourceProvider, "_make_request")
@patch("payments.cybersource.suds.client.Client", new=MagicMock())
def test_provider_redirects_on_success_preauth_payment(mocked_request, mocked_redirect):
    payment = Payment()
    provider = CyberSourceProvider(
        merchant_id=MERCHANT_ID, password=PASSWORD, org_id=ORG_ID, capture=False
    )
    transaction_id = 1234
    xid = "abc"
    payment.attrs.xid = xid

    response = MagicMock()
    response.requestID = transaction_id
    response.reasonCode = ACCEPTED
    mocked_request.return_value = response

    request = MagicMock()
    request.POST = {"MD": xid}
    request.GET = {
        "token": signing.dumps(
            {
                "expiration": {"year": 2023, "month": 9},
                "name": "John Doe",
                "number": "371449635398431",
                "cvv2": "123",
            }
        )
    }
    provider.process_data(payment, request)
    assert payment.status == PaymentStatus.PREAUTH
    assert payment.captured_amount == 0
    assert payment.transaction_id == transaction_id


@patch("payments.cybersource.redirect")
@patch.object(CyberSourceProvider, "_make_request")
@patch("payments.cybersource.suds.client.Client", new=MagicMock())
def test_provider_redirects_on_failure(mocked_request, mocked_redirect, provider):
    payment, prov = provider
    transaction_id = 1234
    xid = "abc"
    payment.attrs.xid = xid

    response = MagicMock()
    response.requestID = transaction_id
    response.reasonCode = "test code"
    mocked_request.return_value = response

    request = MagicMock()
    request.POST = {"MD": xid}
    request.GET = {
        "token": signing.dumps(
            {
                "expiration": {"year": 2023, "month": 9},
                "name": "John Doe",
                "number": "371449635398431",
                "cvv2": "123",
            }
        )
    }
    prov.process_data(payment, request)
    assert payment.status == PaymentStatus.ERROR
    assert payment.captured_amount == 0
    assert payment.transaction_id == transaction_id
