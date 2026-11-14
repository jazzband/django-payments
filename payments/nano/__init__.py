from __future__ import annotations

import secrets
from urllib.error import URLError

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseRedirect

from payments import PaymentStatus
from payments.core import BasicProvider

from . import binding
from .forms import NanoPaymentForm


class NanoProvider(BasicProvider):
    """Payment provider for Nano (XNO).

    The customer's wallet sends the exact amount straight to ``account``; this
    backend never holds a key or a seed and never sends funds. Each payment gets
    a random order id, and the customer's send block must set its
    ``representative`` to an account derived from that order id, the
    destination and the exact amount, so one block can only pay one order. The
    customer then submits the block hash, which is read from the node at
    ``node_url`` and stored as the payment's ``transaction_id``; a hash already
    stored on another payment is refused, also after a restart.

    Payments must use the currency ``XNO``; the amount in raw is derived from
    ``payment.total`` (1 XNO = 10**30 raw).

    This backend does not support pre-authorization, refunds or fraud detection.

    :param account: The ``nano_`` account that receives payments. Its checksum is
        verified.
    :param node_url: URL of a Nano node RPC endpoint you trust (https, or http on
        a loopback address).
    :param timeout: Seconds to wait for the node.
    """

    def __init__(self, account, node_url, timeout=10.0, **kwargs) -> None:
        super().__init__(**kwargs)
        if not self._capture:
            raise ImproperlyConfigured("Nano does not support pre-authorization.")
        try:
            self.account = binding.normalize_account(account)
            self.node_url = binding.check_node_url(node_url)
        except ValueError as e:
            raise ImproperlyConfigured(str(e)) from e
        self.timeout = timeout

    def get_price_raw(self, payment) -> int:
        if payment.currency != "XNO":
            raise ImproperlyConfigured(
                f"Nano payments must use the currency XNO, not {payment.currency}."
            )
        return binding.xno_to_raw(payment.total)

    def get_order_id(self, payment) -> str:
        """Return the payment's random order id, creating it on first use."""
        order_id = getattr(payment.attrs, "nano_order_id", None)
        if not order_id:
            order_id = secrets.token_hex(16)
            payment.attrs.nano_order_id = order_id
            payment.save()
        return order_id

    def get_nano_request(self, payment) -> dict:
        """What the customer's wallet must send for this payment."""
        price_raw = self.get_price_raw(payment)
        order_id = self.get_order_id(payment)
        return {
            "pay_to": self.account,
            "amount_raw": str(price_raw),
            "representative": binding.commitment_representative(
                order_id, self.account, price_raw
            ),
        }

    def get_form(self, payment, data=None):
        nano_request = self.get_nano_request(payment)
        if payment.status == PaymentStatus.WAITING:
            payment.change_status(PaymentStatus.INPUT)
        return NanoPaymentForm(
            data=data,
            action=self.get_return_url(payment),
            method="post",
            provider=self,
            payment=payment,
            hidden_inputs=False,
            nano_request=nano_request,
        )

    def is_block_used(self, payment, block_hash: str) -> bool:
        """Whether another payment already holds this block hash."""
        return (
            type(payment)
            ._default_manager.filter(transaction_id=block_hash)
            .exclude(pk=payment.pk)
            .exists()
        )

    def verify(self, payment, block_hash: str) -> str:
        price_raw = self.get_price_raw(payment)
        order_id = self.get_order_id(payment)
        try:
            block_info = binding.fetch_block_info(
                self.node_url, block_hash, timeout=self.timeout
            )
        except (URLError, OSError, ValueError):
            return binding.INCONCLUSIVE
        return binding.check_block(
            block_info, pay_to=self.account, price_raw=price_raw, order_id=order_id
        )

    def process_data(self, payment, request):
        if payment.status == PaymentStatus.CONFIRMED:
            return HttpResponseRedirect(payment.get_success_url())
        form = NanoPaymentForm(data=request.POST, hidden_inputs=False)
        if not form.is_valid():
            return HttpResponseRedirect(payment.get_failure_url())
        block_hash = form.cleaned_data["block_hash"]
        if self.is_block_used(payment, block_hash):
            return HttpResponseRedirect(payment.get_failure_url())
        if self.verify(payment, block_hash) != binding.MATCHED:
            return HttpResponseRedirect(payment.get_failure_url())
        payment.transaction_id = block_hash
        payment.captured_amount = payment.total
        payment.change_status(PaymentStatus.CONFIRMED)
        payment.save()
        return HttpResponseRedirect(payment.get_success_url())
