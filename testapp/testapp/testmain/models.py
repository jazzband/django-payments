from __future__ import annotations

from typing import TYPE_CHECKING

from payments import PurchasedItem
from payments.models import BasePayment

if TYPE_CHECKING:
    from collections.abc import Iterator


class Payment(BasePayment):
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
