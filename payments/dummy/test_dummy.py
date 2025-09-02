from __future__ import annotations

from unittest.mock import MagicMock
from urllib.error import URLError
from urllib.parse import urlencode

import pytest

from payments import FraudStatus
from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded

from . import DummyProvider

VARIANT = "dummy-3ds"


class Payment:
    id = 1
    variant = VARIANT
    currency = "USD"
    total = 100
    status = PaymentStatus.WAITING
    fraud_status = ""
    captured_amount = 0

    def get_process_url(self):
        return "http://example.com"

    def get_failure_url(self):
        return "http://cancel.com"

    def get_success_url(self):
        return "http://success.com"

    def change_status(self, new_status):
        self.status = new_status

    def change_fraud_status(self, fraud_status):
        self.fraud_status = fraud_status


@pytest.fixture
def payment():
    return Payment()


def test_process_data_supports_verification_result(payment):
    provider = DummyProvider()
    verification_status = PaymentStatus.CONFIRMED
    request = MagicMock()
    request.GET = {"verification_result": verification_status}
    response = provider.process_data(payment, request)
    assert payment.status == verification_status
    assert payment.captured_amount == 100
    assert response.status_code == 302
    assert response["location"] == payment.get_success_url()


def test_process_data_redirects_to_success_on_payment_success(payment):
    payment.status = PaymentStatus.PREAUTH
    provider = DummyProvider()
    request = MagicMock()
    request.GET = {}
    response = provider.process_data(payment, request)
    assert response["location"] == payment.get_success_url()


def test_process_data_redirects_to_failure_on_payment_failure(payment):
    payment.status = PaymentStatus.REJECTED
    provider = DummyProvider()
    request = MagicMock()
    request.GET = {}
    response = provider.process_data(payment, request)
    assert response["location"] == payment.get_failure_url()


def test_provider_supports_non_3ds_transactions(payment):
    provider = DummyProvider()
    data = {
        "status": PaymentStatus.PREAUTH,
        "fraud_status": FraudStatus.UNKNOWN,
        "gateway_response": "3ds-disabled",
        "verification_result": "",
    }
    with pytest.raises(RedirectNeeded) as exc:
        provider.get_form(payment, data)
    assert exc.value.args[0] == payment.get_success_url()


def test_provider_raises_verification_result_needed_on_success(payment):
    provider = DummyProvider()
    data = {
        "status": PaymentStatus.WAITING,
        "fraud_status": FraudStatus.UNKNOWN,
        "gateway_response": "3ds-redirect",
    }
    form = provider.get_form(payment, data)
    assert not form.is_valid()


def test_provider_supports_3ds_redirect(payment):
    provider = DummyProvider()
    verification_result = PaymentStatus.CONFIRMED
    data = {
        "status": PaymentStatus.WAITING,
        "fraud_status": FraudStatus.UNKNOWN,
        "gateway_response": "3ds-redirect",
        "verification_result": verification_result,
    }
    params = urlencode({"verification_result": verification_result})
    expected_redirect = f"{payment.get_process_url()}?{params}"

    with pytest.raises(RedirectNeeded) as exc:
        provider.get_form(payment, data)
    assert exc.value.args[0] == expected_redirect


def test_provider_supports_gateway_failure(payment):
    provider = DummyProvider()
    data = {
        "status": PaymentStatus.WAITING,
        "fraud_status": FraudStatus.UNKNOWN,
        "gateway_response": "failure",
        "verification_result": "",
    }
    with pytest.raises(URLError):
        provider.get_form(payment, data)


def test_provider_raises_redirect_needed_on_success(payment):
    provider = DummyProvider()
    data = {
        "status": PaymentStatus.PREAUTH,
        "fraud_status": FraudStatus.UNKNOWN,
        "gateway_response": "3ds-disabled",
        "verification_result": "",
    }
    with pytest.raises(RedirectNeeded) as exc:
        provider.get_form(payment, data)
    assert exc.value.args[0] == payment.get_success_url()


def test_provider_raises_redirect_needed_on_failure(payment):
    provider = DummyProvider()
    data = {
        "status": PaymentStatus.ERROR,
        "fraud_status": FraudStatus.UNKNOWN,
        "gateway_response": "3ds-disabled",
        "verification_result": "",
    }
    with pytest.raises(RedirectNeeded) as exc:
        provider.get_form(payment, data)
    assert exc.value.args[0] == payment.get_failure_url()


def test_provider_raises_payment_error(payment):
    provider = DummyProvider()
    data = {
        "status": PaymentStatus.PREAUTH,
        "fraud_status": FraudStatus.UNKNOWN,
        "gateway_response": "payment-error",
        "verification_result": "",
    }
    with pytest.raises(PaymentError):
        provider.get_form(payment, data)


def test_provider_switches_payment_status_on_get_form(payment):
    provider = DummyProvider()
    provider.get_form(payment, data={})
    assert payment.status == PaymentStatus.INPUT
