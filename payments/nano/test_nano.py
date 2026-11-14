from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import QueryDict

from payments import PaymentStatus
from payments.models import PaymentAttributeProxy

from . import NanoProvider
from .binding import commitment_representative

ACCOUNT = "nano_1111111111111111111111111111111111111111111111111111hifc8npp"
NODE_URL = "https://node.example/rpc"
BLOCK_HASH = "B" * 64
PRICE_RAW = 5 * 10**28


class Payment:
    pk = 1
    currency = "XNO"
    total = Decimal("0.05")
    status = PaymentStatus.WAITING
    token = "5a4dae68-2715-4b1e-8bb2-2c2dbe9255f6"
    variant = "nano"
    transaction_id = ""
    captured_amount = Decimal(0)

    # Hashes held by other payments; shared across instances like a table.
    _default_manager = MagicMock()

    def __init__(self) -> None:
        self.extra_data = ""
        self.saved = 0

    @property
    def attrs(self) -> PaymentAttributeProxy:
        return PaymentAttributeProxy(self)

    def change_status(self, status: str, message: str = "") -> None:
        self.status = status

    def get_failure_url(self) -> str:
        return "http://cancel.com"

    def get_process_url(self) -> str:
        return "/payments/process/token/"

    def get_success_url(self) -> str:
        return "http://success.com"

    def save(self) -> None:
        self.saved += 1


def hash_used_elsewhere(used: bool) -> None:
    queryset = Payment._default_manager.filter.return_value.exclude.return_value
    queryset.exists.return_value = used


@pytest.fixture
def payment() -> Payment:
    Payment._default_manager.reset_mock()
    hash_used_elsewhere(False)
    return Payment()


@pytest.fixture
def provider() -> NanoProvider:
    return NanoProvider(account=ACCOUNT, node_url=NODE_URL)


def send_block(payment: Payment, provider: NanoProvider, **overrides) -> dict:
    info = {
        "subtype": "send",
        "confirmed": "true",
        "amount": str(PRICE_RAW),
        "contents": {
            "link_as_account": ACCOUNT,
            "representative": commitment_representative(
                provider.get_order_id(payment), ACCOUNT, PRICE_RAW
            ),
        },
    }
    info.update(overrides)
    return info


def post(block_hash: str = BLOCK_HASH) -> MagicMock:
    request = MagicMock()
    request.POST = QueryDict(mutable=True)
    request.POST["block_hash"] = block_hash
    return request


def test_bad_configuration_refused() -> None:
    with pytest.raises(ImproperlyConfigured):
        NanoProvider(account=ACCOUNT[:-1] + "q", node_url=NODE_URL)
    with pytest.raises(ImproperlyConfigured):
        NanoProvider(account=ACCOUNT, node_url="http://node.example:7076")
    with pytest.raises(ImproperlyConfigured):
        NanoProvider(account=ACCOUNT, node_url=NODE_URL, capture=False)


def test_form_shows_bound_request(payment: Payment, provider: NanoProvider) -> None:
    form = provider.get_form(payment)
    order_id = payment.attrs.nano_order_id
    assert len(order_id) == 32
    assert payment.status == PaymentStatus.INPUT
    assert form.nano_request == {
        "pay_to": ACCOUNT,
        "amount_raw": str(PRICE_RAW),
        "representative": commitment_representative(order_id, ACCOUNT, PRICE_RAW),
    }
    # The order id is kept, so the request does not change between visits.
    assert provider.get_form(payment).nano_request == form.nano_request


def test_orders_get_different_representatives(provider: NanoProvider) -> None:
    first = provider.get_nano_request(Payment())
    second = provider.get_nano_request(Payment())
    assert first["representative"] != second["representative"]


def test_non_xno_currency_refused(payment: Payment, provider: NanoProvider) -> None:
    payment.currency = "USD"
    with pytest.raises(ImproperlyConfigured):
        provider.get_form(payment)


def test_process_data_confirms(payment: Payment, provider: NanoProvider) -> None:
    info = send_block(payment, provider)
    with patch("payments.nano.binding.fetch_block_info", return_value=info) as fetch:
        response = provider.process_data(payment, post(BLOCK_HASH.lower()))
    fetch.assert_called_once_with(NODE_URL, BLOCK_HASH, timeout=10.0)
    assert response["Location"] == "http://success.com"
    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.transaction_id == BLOCK_HASH
    assert payment.captured_amount == Decimal("0.05")


def test_block_for_another_payment_refused(
    payment: Payment, provider: NanoProvider
) -> None:
    info = send_block(Payment(), provider)
    with patch("payments.nano.binding.fetch_block_info", return_value=info):
        response = provider.process_data(payment, post())
    assert response["Location"] == "http://cancel.com"
    assert payment.status == PaymentStatus.WAITING
    assert payment.transaction_id == ""


def test_hash_stored_on_another_payment_refused(
    payment: Payment, provider: NanoProvider
) -> None:
    hash_used_elsewhere(True)
    info = send_block(payment, provider)
    with patch("payments.nano.binding.fetch_block_info", return_value=info) as fetch:
        response = provider.process_data(payment, post())
    Payment._default_manager.filter.assert_called_once_with(transaction_id=BLOCK_HASH)
    fetch.assert_not_called()
    assert response["Location"] == "http://cancel.com"
    assert payment.status == PaymentStatus.WAITING


def test_wrong_amount_refused(payment: Payment, provider: NanoProvider) -> None:
    info = send_block(payment, provider, amount=str(PRICE_RAW - 1))
    with patch("payments.nano.binding.fetch_block_info", return_value=info):
        response = provider.process_data(payment, post())
    assert response["Location"] == "http://cancel.com"
    assert payment.status == PaymentStatus.WAITING


def test_unconfirmed_block_can_be_retried(
    payment: Payment, provider: NanoProvider
) -> None:
    info = send_block(payment, provider, confirmed="false")
    with patch("payments.nano.binding.fetch_block_info", return_value=info):
        provider.process_data(payment, post())
    assert payment.status == PaymentStatus.WAITING
    info["confirmed"] = "true"
    with patch("payments.nano.binding.fetch_block_info", return_value=info):
        provider.process_data(payment, post())
    assert payment.status == PaymentStatus.CONFIRMED


def test_node_error_is_not_a_payment(payment: Payment, provider: NanoProvider) -> None:
    with patch("payments.nano.binding.fetch_block_info", side_effect=OSError("down")):
        response = provider.process_data(payment, post())
    assert response["Location"] == "http://cancel.com"
    assert payment.status == PaymentStatus.WAITING


def test_malformed_hash_refused(payment: Payment, provider: NanoProvider) -> None:
    with patch("payments.nano.binding.fetch_block_info") as fetch:
        response = provider.process_data(payment, post("not-a-hash"))
    fetch.assert_not_called()
    assert response["Location"] == "http://cancel.com"
