from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from payments import PaymentStatus
from payments import RedirectNeeded

from . import AuthorizeNetProvider

LOGIN_ID = "abcd1234"
TRANSACTION_KEY = "1234abdd"

PROCESS_DATA = {
    "number": "4007000000027",
    "expiration_0": "5",
    "expiration_1": date.today().year + 1,
    "cvv2": "123",
}

STATUS_CONFIRMED = "1"
STATUS_DECLINED = "2"
ERROR_PROCESSING = "3"


class Payment(Mock):
    id = 1
    variant = "authorizenet"
    currency = "USD"
    total = 100
    status = PaymentStatus.WAITING
    transaction_id = None
    captured_amount = 0
    message = ""

    def get_process_url(self):
        return "http://example.com"

    def get_failure_url(self):
        return "http://cancel.com"

    def get_success_url(self):
        return "http://success.com"

    def change_status(self, status, message=""):
        self.status = status
        self.message = message


@pytest.fixture
def payment():
    return Payment()


def test_provider_redirects_to_success_on_payment_success(payment):
    provider = AuthorizeNetProvider(login_id=LOGIN_ID, transaction_key=TRANSACTION_KEY)

    response_data = [
        STATUS_CONFIRMED,
        "",
        "",
        "This transaction has been approved.",
        "",
        "",
        "1234",
    ]

    with patch("requests.post") as mocked_post:
        post = MagicMock()
        post.text = "|".join(response_data)
        mocked_post.return_value = post
        with pytest.raises(RedirectNeeded) as exc:
            provider.get_form(payment, data=PROCESS_DATA)
        assert str(exc.value) == payment.get_success_url()

    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.captured_amount == payment.total


@pytest.mark.skip
def test_provider_shows_validation_error_message(payment):
    provider = AuthorizeNetProvider(login_id=LOGIN_ID, transaction_key=TRANSACTION_KEY)

    error_msg = "The merchant does not accept this type of credit card."
    response_data = [ERROR_PROCESSING, "", "", error_msg, "", "", "1234"]

    with patch("requests.post") as mocked_post:
        post = MagicMock()
        post.text = "|".join(response_data)
        mocked_post.return_value = post
        form = provider.get_form(payment, data=PROCESS_DATA)
        assert form.errors["__all__"][0] == error_msg
        assert not form.is_valid()

    assert payment.status == "error"
    assert payment.captured_amount == 0
    assert payment.message == error_msg


@pytest.mark.skip
def test_provider_shows_rejection_error_message(payment):
    provider = AuthorizeNetProvider(login_id=LOGIN_ID, transaction_key=TRANSACTION_KEY)

    error_msg = " This transaction has been declined."
    response_data = [STATUS_DECLINED, "", "", error_msg, "", "", "1234"]

    with patch("requests.post") as mocked_post:
        post = MagicMock()
        post.text = "|".join(response_data)
        mocked_post.return_value = post
        form = provider.get_form(payment, data=PROCESS_DATA)
        assert form.errors["__all__"][0] == error_msg
        assert not form.is_valid()

    assert payment.status == "rejected"
    assert payment.captured_amount == 0
    assert payment.message == error_msg
