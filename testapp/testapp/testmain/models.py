from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

from payments import PurchasedItem
from payments import WalletStatus
from payments.models import BasePayment
from payments.models import BaseWallet

if TYPE_CHECKING:
    from collections.abc import Iterator


class Wallet(BaseWallet):
    payment_provider = models.CharField(max_length=50)

    class Meta:
        app_label = "testmain"


class Payment(BasePayment):
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )

    class Meta:
        app_label = "testmain"

    def get_failure_url(self) -> str:
        return "http://localhost:8000/test/payment-failure"

    def get_success_url(self) -> str:
        return "http://localhost:8000/test/payment-success"

    def get_purchased_items(self) -> Iterator[PurchasedItem]:
        yield PurchasedItem(
            name=self.description,
            sku="BSKV",
            quantity=1,
            price=self.total,
            currency=self.currency,
        )

    def get_renew_token(self):
        if self.wallet and self.wallet.status == WalletStatus.ACTIVE:
            return self.wallet.token
        return None

    def set_renew_token(self, token, **kwargs):
        if not self.wallet:
            self.wallet = Wallet.objects.create(payment_provider=self.variant)
            self.save(update_fields=["wallet"])
        self.wallet.token = token
        self.wallet.extra_data.update(kwargs)
        self.wallet.save(update_fields=["token", "extra_data"])
        self.wallet.activate()
