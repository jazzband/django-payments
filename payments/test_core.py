from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import NonCallableMock
from unittest.mock import patch

import pytest

from payments import core

from . import PaymentStatus
from .forms import CreditCardPaymentFormWithName
from .forms import PaymentForm
from .models import BasePayment


@patch("payments.core.PAYMENT_HOST", new_callable=NonCallableMock)
def test_text_get_base_url(host):
    host.__str__ = lambda x: "example.com/string"
    assert core.get_base_url() == "https://example.com/string"


@patch("payments.core.PAYMENT_HOST")
def test_callable_get_base_url(host):
    host.return_value = "example.com/callable"
    assert core.get_base_url() == "https://example.com/callable"


def test_provider_factory():
    core.provider_factory("default")


def test_provider_does_not_exist():
    with pytest.raises(
        ValueError,
        match="Payment variant does not exist: fake_provider",
    ):
        core.provider_factory("fake_provider")


class Payment(BasePayment):
    """
    Concrete model class for testing.
    Instantiating an abstract model is deprecated in newer versions of Django.
    """


def test_payment_attributes():
    payment = Payment(extra_data='{"attr1": "test1", "attr2": "test2"}')
    assert payment.attrs.attr1 == "test1"
    assert payment.attrs.attr2 == "test2"
    assert getattr(payment.attrs, "attr5", None) is None
    assert not hasattr(payment.attrs, "attr7")


def test_capture_with_wrong_status():
    payment = Payment(variant="default", status=PaymentStatus.WAITING)
    with pytest.raises(
        ValueError,
        match="Only pre-authorized payments can be captured.",
    ):
        payment.capture()


@patch("payments.dummy.DummyProvider.capture")
def test_capture_preauth_successfully(mocked_capture_method):
    amount = Decimal("20")
    with patch.object(BasePayment, "save"):
        mocked_capture_method.return_value = amount
        payment = Payment(variant="default", status=PaymentStatus.PREAUTH)
        payment.capture(amount)

        assert payment.status == PaymentStatus.CONFIRMED
        assert payment.captured_amount == amount
    assert mocked_capture_method.call_count == 1


@patch("payments.dummy.DummyProvider.capture")
def test_capture_preauth_without_amount(mocked_capture_method):
    with patch.object(BasePayment, "save"):
        mocked_capture_method.return_value = None
        captured_amount = Decimal("100")
        payment = Payment(
            variant="default",
            status=PaymentStatus.PREAUTH,
            captured_amount=captured_amount,
        )
        payment.capture(None)

        assert payment.status == PaymentStatus.PREAUTH
        assert payment.captured_amount == captured_amount
    assert mocked_capture_method.call_count == 1


def test_release_with_wrong_status():
    payment = Payment(variant="default", status=PaymentStatus.WAITING)
    with pytest.raises(
        ValueError,
        match="Only pre-authorized payments can be released.",
    ):
        payment.release()


@patch("payments.dummy.DummyProvider.release")
def test_release_preauth_successfully(mocked_release_method):
    with patch.object(BasePayment, "save"):
        payment = Payment(variant="default", status=PaymentStatus.PREAUTH)
        payment.release()
        assert payment.status == PaymentStatus.REFUNDED
    assert mocked_release_method.call_count == 1


def test_refund_with_wrong_status():
    payment = Payment(variant="default", status=PaymentStatus.WAITING)
    with pytest.raises(ValueError, match="Only charged payments can be refunded."):
        payment.refund()


def test_refund_too_high_amount():
    payment = Payment(
        variant="default",
        status=PaymentStatus.CONFIRMED,
        captured_amount=Decimal("100"),
    )
    with pytest.raises(
        ValueError,
        match="Refund amount can not be greater then captured amount",
    ):
        payment.refund(Decimal("200"))


@patch("payments.dummy.DummyProvider.refund")
def test_refund_without_amount(mocked_refund_method):
    captured_amount = Decimal("200")
    with patch.object(BasePayment, "save"):
        mocked_refund_method.return_value = captured_amount
        payment = Payment(
            variant="default",
            status=PaymentStatus.CONFIRMED,
            captured_amount=captured_amount,
        )
        payment.refund()

        assert payment.status == PaymentStatus.REFUNDED
        assert payment.captured_amount == Decimal("0")
    assert mocked_refund_method.call_count == 1


@patch("payments.dummy.DummyProvider.refund")
def test_refund_partial_success(mocked_refund_method):
    refund_amount = Decimal("100")
    captured_amount = Decimal("200")
    with patch.object(BasePayment, "save"):
        mocked_refund_method.return_value = refund_amount
        payment = Payment(
            variant="default",
            status=PaymentStatus.CONFIRMED,
            captured_amount=captured_amount,
        )
        payment.refund(refund_amount)

        assert payment.status == PaymentStatus.CONFIRMED
        assert payment.captured_amount == Decimal("100")
    assert mocked_refund_method.call_count == 1


@patch("payments.dummy.DummyProvider.refund")
def test_refund_fully_success(mocked_refund_method):
    refund_amount = Decimal("200")
    captured_amount = Decimal("200")
    with patch.object(BasePayment, "save"):
        mocked_refund_method.return_value = refund_amount
        payment = Payment(
            variant="default",
            status=PaymentStatus.CONFIRMED,
            captured_amount=captured_amount,
        )
        payment.refund(refund_amount)

        assert payment.status == PaymentStatus.REFUNDED
        assert payment.captured_amount == Decimal("0")
    assert mocked_refund_method.call_count == 1


@pytest.fixture
def credit_card_data():
    return {
        "name": "John Doe",
        "number": "4716124728800975",
        "expiration_0": "5",
        "expiration_1": date.today().year + 1,
        "cvv2": "123",
    }


def test_form_verifies_card_number(credit_card_data):
    form = CreditCardPaymentFormWithName(data=credit_card_data)
    assert form.is_valid()


def test_form_raises_error_for_invalid_card_number(credit_card_data):
    data = dict(credit_card_data, number="1112223334445556")
    form = CreditCardPaymentFormWithName(data=data)
    assert not form.is_valid()
    assert "number" in form.errors


def test_form_raises_error_for_invalid_cvv2(credit_card_data):
    data = dict(credit_card_data, cvv2="12345")
    form = CreditCardPaymentFormWithName(data=data)
    assert not form.is_valid()
    assert "cvv2" in form.errors


def test_form_contains_hidden_fields():
    data = {
        "field1": "value1",
        "field2": "value2",
        "field3": "value3",
        "field4": "value4",
    }
    form = PaymentForm(data=data, hidden_inputs=True)
    assert len(form.fields) == len(data)
    assert form.fields["field1"].initial == "value1"


def test_mastercard():
    assert core.get_credit_card_issuer("2720999018275485") == (
        "mastercard",
        "MasterCard",
    )
    assert core.get_credit_card_issuer("5101395940513451") == (
        "mastercard",
        "MasterCard",
    )
    assert core.get_credit_card_issuer("5469166706524768") == (
        "mastercard",
        "MasterCard",
    )


def test_visa():
    assert core.get_credit_card_issuer("4929299255922609") == ("visa", "VISA")
    assert core.get_credit_card_issuer("4539883983691685") == ("visa", "VISA")
    assert core.get_credit_card_issuer("4916396455393611281") == ("visa", "VISA")


def test_discover():
    assert core.get_credit_card_issuer("6011281400356614") == ("discover", "Discover")
    assert core.get_credit_card_issuer("6011223438090674") == ("discover", "Discover")
    assert core.get_credit_card_issuer("6011509478386387430") == (
        "discover",
        "Discover",
    )


def test_amex():
    assert core.get_credit_card_issuer("341841172626538") == (
        "amex",
        "American Express",
    )
    assert core.get_credit_card_issuer("348710065929999") == (
        "amex",
        "American Express",
    )
    assert core.get_credit_card_issuer("341473920579841") == (
        "amex",
        "American Express",
    )
