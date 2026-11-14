from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from payments.forms import PaymentForm

from .binding import normalize_block_hash


class NanoPaymentForm(PaymentForm):
    """Shows where and how much to send, and takes the hash of the send block."""

    block_hash = forms.CharField(
        label=_("Send block hash"),
        min_length=64,
        max_length=64,
        help_text=_("The hash of the send block your wallet created."),
    )

    def __init__(self, *args, nano_request=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        #: ``pay_to``, ``amount_raw`` and ``representative`` for the template.
        self.nano_request = nano_request or {}

    def clean_block_hash(self) -> str:
        try:
            return normalize_block_hash(self.cleaned_data["block_hash"])
        except ValueError as e:
            raise forms.ValidationError(str(e)) from e
