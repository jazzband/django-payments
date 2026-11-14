"""Nano (XNO) helpers for :class:`payments.nano.NanoProvider`.

Standard library only: no key, no seed, no signing. Amounts are integer raw
throughout (1 XNO = 10**30 raw).

A Nano block carries no memo, so a payment is bound to its order through the
send block's ``representative`` field: the payer sets it to an account derived
from ``SHA256("xno-binding/v1/rep|" + order_id + "|" + pay_to + "|" + raw)``.
The payer signs that value, so a block made for one order never verifies for
another, and the amount and destination are covered by the same commitment.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import urllib.request
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

XNO_RAW = 10**30
"""Raw units in one XNO."""

_ALPHABET = "13456789abcdefghijkmnopqrstuwxyz"
_HASH_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
_MAX_REPLY_BYTES = 64 * 1024

MATCHED = "matched"
INCONCLUSIVE = "inconclusive"
NOT_PAYMENT = "refusable_not_payment"
WRONG_AMOUNT = "refusable_wrong_amount"
NOT_BOUND = "refusable_not_bound"


def _encode(n: int, chars: int) -> str:
    out = []
    for _ in range(chars):
        out.append(_ALPHABET[n & 31])
        n >>= 5
    return "".join(reversed(out))


def public_key_to_account(public_key: bytes) -> str:
    """Encode a 32-byte public key as a ``nano_`` account with its checksum."""
    if len(public_key) != 32:
        raise ValueError("A Nano public key is 32 bytes.")
    body = _encode(int.from_bytes(public_key, "big"), 52)
    digest = hashlib.blake2b(public_key, digest_size=5).digest()[::-1]
    return "nano_" + body + _encode(int.from_bytes(digest, "big"), 8)


def normalize_account(account: str) -> str:
    """Return ``account`` as a ``nano_`` address, or raise ``ValueError``.

    The blake2b checksum in the last eight characters is verified, so a
    mistyped address is refused instead of receiving funds.
    """
    account = str(account)
    if account.startswith("xrb_"):
        account = "nano_" + account[4:]
    if not account.startswith("nano_") or len(account) != 65:
        raise ValueError("Not a Nano account.")
    body = account[5:]
    if body[0] not in "13" or any(ch not in _ALPHABET for ch in body):
        raise ValueError("Not a Nano account.")
    n = 0
    for ch in body[:52]:
        n = n * 32 + _ALPHABET.index(ch)
    public_key = n.to_bytes(32, "big")
    if public_key_to_account(public_key) != account:
        raise ValueError("Nano account checksum does not match.")
    return account


def xno_to_raw(amount: Decimal) -> int:
    """Convert an exact XNO amount to raw, refusing anything below one raw."""
    if not isinstance(amount, Decimal) or not amount.is_finite():
        raise ValueError("The amount must be a finite Decimal.")
    if amount <= 0:
        raise ValueError("The amount must be positive.")
    _sign, digits, exponent = amount.as_tuple()
    assert isinstance(exponent, int)
    value = int("".join(map(str, digits)))
    shift = exponent + 30
    if shift >= 0:
        return value * 10**shift
    if value % 10**-shift:
        raise ValueError("The amount is finer than one raw.")
    return value // 10**-shift


def order_commitment(order_id: str, pay_to: str, price_raw: int) -> bytes:
    """SHA-256 commitment to the order, destination and exact price."""
    if isinstance(price_raw, bool) or not isinstance(price_raw, int):
        raise TypeError("price_raw must be an int of raw.")
    message = "|".join(("xno-binding/v1/rep", order_id, pay_to, str(price_raw)))
    return hashlib.sha256(message.encode()).digest()


def commitment_representative(order_id: str, pay_to: str, price_raw: int) -> str:
    """The representative a payer sets on the send block for this order."""
    return public_key_to_account(order_commitment(order_id, pay_to, price_raw))


def normalize_block_hash(block_hash: str) -> str:
    """Return the block hash upper-cased, or raise ``ValueError``."""
    if not isinstance(block_hash, str) or not _HASH_RE.match(block_hash.strip()):
        raise ValueError("A block hash is 64 hexadecimal characters.")
    return block_hash.strip().upper()


def check_block(block_info: Any, *, pay_to: str, price_raw: int, order_id: str) -> str:
    """Judge a node's ``block_info`` reply (``json_block=true``) for one order.

    Returns :data:`MATCHED` only for a confirmed send of exactly ``price_raw``
    to ``pay_to`` whose representative is this order's commitment.
    """
    if not isinstance(block_info, dict) or "error" in block_info:
        return INCONCLUSIVE
    contents = block_info.get("contents")
    if not isinstance(contents, dict):
        return INCONCLUSIVE
    if block_info.get("subtype") != "send":
        return NOT_PAYMENT
    try:
        destination = normalize_account(contents.get("link_as_account", ""))
    except ValueError:
        return INCONCLUSIVE
    if destination != pay_to:
        return NOT_PAYMENT
    if str(block_info.get("confirmed")).lower() != "true":
        return INCONCLUSIVE
    amount = block_info.get("amount")
    if not isinstance(amount, str) or not amount.isdigit() or len(amount) > 40:
        return INCONCLUSIVE
    if int(amount) != price_raw:
        return WRONG_AMOUNT
    expected = commitment_representative(order_id, pay_to, price_raw)
    try:
        representative = normalize_account(contents.get("representative", ""))
    except ValueError:
        return NOT_BOUND
    if representative != expected:
        return NOT_BOUND
    return MATCHED


def check_node_url(url: str) -> str:
    """Refuse a node URL that would send RPC in clear text off this host."""
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.hostname:
        return url
    if parts.scheme == "http" and parts.hostname:
        if parts.hostname == "localhost":
            return url
        try:
            if ipaddress.ip_address(parts.hostname).is_loopback:
                return url
        except ValueError:
            pass
    raise ValueError("The node URL must be https, or http on a loopback address.")


def fetch_block_info(node_url: str, block_hash: str, timeout: float = 10.0) -> Any:
    """Read one block from the operator's node with a bounded request."""
    body = json.dumps(
        {"action": "block_info", "json_block": "true", "hash": block_hash}
    ).encode()
    request = urllib.request.Request(
        check_node_url(node_url),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(_MAX_REPLY_BYTES + 1)
    if len(raw) > _MAX_REPLY_BYTES:
        raise ValueError("The node reply is too large.")
    return json.loads(raw)
