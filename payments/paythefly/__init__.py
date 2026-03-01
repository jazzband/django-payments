from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from decimal import Decimal
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.http import HttpResponseForbidden

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded
from payments.core import BasicProvider

if TYPE_CHECKING:
    from django.http import HttpRequest

    from payments.models import BasePayment

logger = logging.getLogger(__name__)

# Chain configurations
# chain_id -> (symbol, native_token_address, decimals)
CHAIN_CONFIG = {
    56: ("BSC", "0x0000000000000000000000000000000000000000", 18),
    728126428: ("TRON", "T9yD14Nj9j7xAB4dbGeiX9h8unkKHxuWwb", 6),
}

# Webhook transaction types
TX_TYPE_PAYMENT = 1
TX_TYPE_WITHDRAWAL = 2

# EIP-712 type definitions
EIP712_DOMAIN_TYPE = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]

EIP712_PAYMENT_REQUEST_TYPE = [
    {"name": "projectId", "type": "string"},
    {"name": "token", "type": "address"},
    {"name": "amount", "type": "uint256"},
    {"name": "serialNo", "type": "string"},
    {"name": "deadline", "type": "uint256"},
]


def _build_eip712_domain(chain_id: int, verifying_contract: str) -> dict:
    """Build the EIP-712 domain separator data."""
    return {
        "name": "PayTheFlyPro",
        "version": "1",
        "chainId": chain_id,
        "verifyingContract": verifying_contract,
    }


def _sign_typed_data(
    private_key: str,
    chain_id: int,
    verifying_contract: str,
    message: dict,
) -> str:
    """Sign EIP-712 typed data using eth_account.

    Returns the hex-encoded signature prefixed with ``0x``.
    Requires ``eth_account>=0.9.0``.
    """
    from eth_account import Account
    from eth_account.messages import encode_structured_data

    domain = _build_eip712_domain(chain_id, verifying_contract)

    full_message = {
        "types": {
            "EIP712Domain": EIP712_DOMAIN_TYPE,
            "PaymentRequest": EIP712_PAYMENT_REQUEST_TYPE,
        },
        "primaryType": "PaymentRequest",
        "domain": domain,
        "message": message,
    }

    signable = encode_structured_data(full_message)
    signed = Account.sign_message(signable, private_key=private_key)
    sig_hex = signed.signature.hex()
    if not sig_hex.startswith("0x"):
        sig_hex = "0x" + sig_hex
    return sig_hex


def _amount_to_wei(amount: Decimal, decimals: int) -> int:
    """Convert a human-readable amount to raw integer (wei / sun).

    For example, ``Decimal("0.01")`` with 18 decimals returns
    ``10000000000000000``.
    """
    return int(amount * (10**decimals))


def _verify_webhook_signature(data: str, timestamp: int, sign: str, key: str) -> bool:
    """Verify HMAC-SHA256 webhook signature.

    ``sign = HMAC-SHA256(data + "." + str(timestamp), key)``
    """
    message = f"{data}.{timestamp}"
    expected = hmac.new(
        key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, sign)


class PayTheFlyProvider(BasicProvider):
    """Payment provider for `PayTheFly <https://pro.paythefly.com>`_.

    PayTheFly is a crypto payment gateway supporting BSC and TRON chains with
    EIP-712 signed payment links and HMAC-SHA256 webhook verification.

    :param project_id: Project ID from PayTheFly dashboard.
    :param project_key: Project secret key for webhook HMAC verification.
    :param private_key: Ethereum-compatible private key for EIP-712 signing.
        Store this in environment variables, **never** hardcode it.
    :param verifying_contract: The PayTheFlyPro contract address.
    :param chain_id: Blockchain chain ID. ``56`` for BSC (default), ``728126428``
        for TRON.
    :param token_address: Token contract address. Use the chain's native token
        address for native currency payments (e.g. BNB on BSC). Defaults to
        ``None`` which selects the native token for the configured chain.
    :param deadline_seconds: Number of seconds from now until payment link
        expires. Defaults to ``1800`` (30 minutes).
    :param endpoint: PayTheFly base URL. Override for testing.

    Example ``PAYMENT_VARIANTS`` configuration::

        PAYMENT_VARIANTS = {
            "paythefly": (
                "payments.paythefly.PayTheFlyProvider",
                {
                    "project_id": os.environ["PTF_PROJECT_ID"],
                    "project_key": os.environ["PTF_PROJECT_KEY"],
                    "private_key": os.environ["PTF_PRIVATE_KEY"],
                    "verifying_contract": os.environ["PTF_CONTRACT"],
                    "chain_id": 56,
                },
            ),
        }
    """

    _method = "get"
    pay_url = "https://pro.paythefly.com/pay"

    def __init__(
        self,
        project_id: str,
        project_key: str,
        private_key: str,
        verifying_contract: str,
        chain_id: int = 56,
        token_address: str | None = None,
        deadline_seconds: int = 1800,
        endpoint: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        if not self._capture:
            raise ImproperlyConfigured(
                "PayTheFly does not support pre-authorization."
            )

        if chain_id not in CHAIN_CONFIG:
            raise ImproperlyConfigured(
                f"Unsupported chain_id: {chain_id}. "
                f"Supported: {', '.join(str(c) for c in CHAIN_CONFIG)}"
            )

        self.project_id = project_id
        self.project_key = project_key
        self.private_key = private_key
        self.verifying_contract = verifying_contract
        self.chain_id = chain_id
        self.deadline_seconds = deadline_seconds

        _, native_token, _ = CHAIN_CONFIG[chain_id]
        self.token_address = token_address or native_token

        if endpoint:
            self.pay_url = endpoint.rstrip("/") + "/pay"

    @property
    def _chain_decimals(self) -> int:
        return CHAIN_CONFIG[self.chain_id][2]

    def _build_payment_url(self, payment: BasePayment) -> str:
        """Build a signed PayTheFly payment URL for the given payment."""
        serial_no = payment.token
        amount_human = str(payment.total)
        deadline = int(time.time()) + self.deadline_seconds
        amount_wei = _amount_to_wei(payment.total, self._chain_decimals)

        # EIP-712 message to sign (amounts in raw wei)
        message = {
            "projectId": self.project_id,
            "token": self.token_address,
            "amount": amount_wei,
            "serialNo": serial_no,
            "deadline": deadline,
        }

        signature = _sign_typed_data(
            self.private_key,
            self.chain_id,
            self.verifying_contract,
            message,
        )

        # URL query params (amount in human-readable form)
        params = {
            "chainId": self.chain_id,
            "projectId": self.project_id,
            "amount": amount_human,
            "serialNo": serial_no,
            "deadline": deadline,
            "signature": signature,
            "token": self.token_address,
        }

        return f"{self.pay_url}?{urlencode(params)}"

    def get_form(self, payment: BasePayment, data=None):
        """Redirect the user to the PayTheFly payment page.

        This always raises :class:`~payments.RedirectNeeded` because PayTheFly
        uses an external hosted payment page.
        """
        if payment.status == PaymentStatus.WAITING:
            payment.change_status(PaymentStatus.INPUT)

        url = self._build_payment_url(payment)

        # Store the payment URL and deadline in extra_data
        payment.attrs.paythefly_url = url
        payment.attrs.paythefly_deadline = int(time.time()) + self.deadline_seconds
        payment.save()

        raise RedirectNeeded(url)

    def get_hidden_fields(self, payment: BasePayment) -> dict:
        """Return empty dict; PayTheFly uses redirect-based flow."""
        return {}

    def process_data(self, payment: BasePayment, request: HttpRequest) -> HttpResponse:
        """Process incoming webhook notification from PayTheFly.

        Expected JSON body::

            {
                "data": "<json string>",
                "sign": "<hmac hex>",
                "timestamp": <unix int>
            }

        Where ``data`` is a JSON-encoded string containing fields like
        ``serial_no``, ``tx_hash``, ``value``, ``tx_type``, ``confirmed``, etc.

        Response body must contain ``"success"`` for PayTheFly to consider
        the webhook delivered.
        """
        try:
            body = json.loads(request.body)
        except (ValueError, TypeError):
            return HttpResponseBadRequest("Invalid JSON")

        data_str = body.get("data")
        sign = body.get("sign")
        timestamp = body.get("timestamp")

        if not all([data_str, sign, timestamp]):
            return HttpResponseBadRequest("Missing required fields")

        # Verify HMAC-SHA256 signature
        if not _verify_webhook_signature(data_str, timestamp, sign, self.project_key):
            logger.warning(
                "PayTheFly webhook signature mismatch for payment %s",
                payment.pk,
            )
            return HttpResponseForbidden("Invalid signature")

        try:
            webhook_data = json.loads(data_str)
        except (ValueError, TypeError):
            return HttpResponseBadRequest("Invalid data JSON")

        tx_type = webhook_data.get("tx_type")
        confirmed = webhook_data.get("confirmed")
        tx_hash = webhook_data.get("tx_hash", "")
        serial_no = webhook_data.get("serial_no", "")

        # Verify the serial_no matches this payment
        if serial_no and serial_no != payment.token:
            logger.warning(
                "PayTheFly webhook serial_no mismatch: expected %s, got %s",
                payment.token,
                serial_no,
            )
            return HttpResponseForbidden("Serial number mismatch")

        # Store webhook data
        payment.attrs.paythefly_webhook = webhook_data
        payment.transaction_id = tx_hash

        if tx_type == TX_TYPE_PAYMENT:
            if confirmed:
                payment.captured_amount = payment.total
                payment.change_status(PaymentStatus.CONFIRMED)
            else:
                # Transaction seen but not yet confirmed on-chain
                payment.save()
        elif tx_type == TX_TYPE_WITHDRAWAL:
            # Withdrawal webhook — store for reference
            payment.attrs.paythefly_withdrawal = webhook_data
            payment.save()
        else:
            logger.warning("Unknown PayTheFly tx_type: %s", tx_type)
            payment.save()

        # PayTheFly requires the response to contain "success"
        return HttpResponse("success")

    def refund(self, payment: BasePayment, amount=None):
        """Refund is not supported via API — must be done on PayTheFly dashboard.

        Raises :class:`~payments.PaymentError`.
        """
        raise PaymentError(
            "PayTheFly refunds must be initiated from the PayTheFly dashboard."
        )

    def capture(self, payment: BasePayment, amount=None):
        """PayTheFly does not support pre-auth / capture.

        Raises ``NotImplementedError``.
        """
        raise NotImplementedError("PayTheFly does not support capture.")

    def release(self, payment: BasePayment):
        """PayTheFly does not support pre-auth / release.

        Raises ``NotImplementedError``.
        """
        raise NotImplementedError("PayTheFly does not support release.")
