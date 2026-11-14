from __future__ import annotations

from decimal import Decimal

import pytest

from .binding import INCONCLUSIVE
from .binding import MATCHED
from .binding import NOT_BOUND
from .binding import NOT_PAYMENT
from .binding import WRONG_AMOUNT
from .binding import XNO_RAW
from .binding import check_block
from .binding import check_node_url
from .binding import commitment_representative
from .binding import normalize_account
from .binding import normalize_block_hash
from .binding import order_commitment
from .binding import xno_to_raw

# Vectors from xno-call-binding docs/BINDING-STANDARD.md (option C).
BURN = "nano_1111111111111111111111111111111111111111111111111111hifc8npp"
PRICE_RAW = 50000000000000000000000000000
ORDER_ID = "order-0001"
COMMITMENT_HEX = "86e75a339b908cc926a478c1a0e5eb5dd6fc612c1d3251eb661faa78135c36cf"
COMMITMENT_REP = "nano_33q9dassq66es6mcay83n5kypqgpzjikr9bkc9ope9xch1borfphgehj4ozj"


def block(**overrides) -> dict:
    contents = {
        "type": "state",
        "link_as_account": BURN,
        "representative": COMMITMENT_REP,
        **overrides.pop("contents", {}),
    }
    info = {
        "subtype": "send",
        "confirmed": "true",
        "amount": str(PRICE_RAW),
        "contents": contents,
    }
    info.update(overrides)
    return info


def check(info) -> str:
    return check_block(info, pay_to=BURN, price_raw=PRICE_RAW, order_id=ORDER_ID)


def test_valid_account() -> None:
    assert normalize_account(BURN) == BURN
    assert normalize_account("xrb_" + BURN[5:]) == BURN


@pytest.mark.parametrize(
    "value",
    ["", "nano_", "nano_" + "0" * 60, BURN[:-1], BURN[:-1] + "q", 42],
)
def test_bad_account_refused(value) -> None:
    with pytest.raises(ValueError, match="Nano account"):
        normalize_account(value)


def test_raw_is_derived() -> None:
    assert xno_to_raw(Decimal("0.05")) == PRICE_RAW
    assert xno_to_raw(Decimal(1)) == XNO_RAW
    assert xno_to_raw(Decimal("1234567.89")) == 123456789 * 10**28


@pytest.mark.parametrize(
    "value", [Decimal("1e-31"), Decimal(0), Decimal(-1), Decimal("NaN"), 0.05]
)
def test_bad_amount_refused(value) -> None:
    with pytest.raises(ValueError, match="amount"):
        xno_to_raw(value)


def test_standard_vectors() -> None:
    assert order_commitment(ORDER_ID, BURN, PRICE_RAW).hex() == COMMITMENT_HEX
    assert commitment_representative(ORDER_ID, BURN, PRICE_RAW) == COMMITMENT_REP
    assert commitment_representative("order-0002", BURN, PRICE_RAW) != COMMITMENT_REP


def test_price_must_be_int() -> None:
    with pytest.raises(TypeError):
        order_commitment(ORDER_ID, BURN, float(PRICE_RAW))  # type: ignore[arg-type]


def test_matched() -> None:
    assert check(block()) == MATCHED


def test_block_for_another_order_not_bound() -> None:
    other = check_block(block(), pay_to=BURN, price_raw=PRICE_RAW, order_id="o-2")
    assert other == NOT_BOUND
    assert check(block(contents={"representative": BURN})) == NOT_BOUND


def test_wrong_amount() -> None:
    assert check(block(amount=str(PRICE_RAW - 1))) == WRONG_AMOUNT
    assert check(block(amount=str(PRICE_RAW + 1))) == WRONG_AMOUNT


def test_not_a_payment_to_us() -> None:
    other = commitment_representative("x", BURN, 1)
    assert check(block(contents={"link_as_account": other})) == NOT_PAYMENT
    assert check(block(subtype="receive")) == NOT_PAYMENT


@pytest.mark.parametrize(
    "info",
    [
        block(confirmed="false"),
        block(amount="5e28"),
        block(amount="1" * 41),
        {"error": "Block not found"},
        {"subtype": "send"},
        ["not", "an", "object"],
    ],
)
def test_inconclusive(info) -> None:
    assert check(info) == INCONCLUSIVE


def test_block_hash() -> None:
    assert normalize_block_hash("a" * 64) == "A" * 64
    for value in ("a" * 63, "g" * 64, ""):
        with pytest.raises(ValueError, match="block hash"):
            normalize_block_hash(value)


def test_node_url() -> None:
    assert check_node_url("https://node.example/rpc")
    assert check_node_url("http://127.0.0.1:7076")
    assert check_node_url("http://localhost:7076")
    for url in ("http://node.example:7076", "ftp://127.0.0.1", "https://"):
        with pytest.raises(ValueError, match="node URL"):
            check_node_url(url)
