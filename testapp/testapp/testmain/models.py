# Create your models here.
from decimal import Decimal

from payments import PurchasedItem
from payments.models import BasePayment


class Payment(BasePayment):
    def get_failure_url(self):
        return "http://example.com/failure/"

    def get_success_url(self):
        return "http://example.com/success/"

    def get_purchased_items(self):
        yield PurchasedItem(
            name="The Hound of the Baskervilles",
            sku="BSKV",
            quantity=9,
            price=Decimal(10),
            currency="USD",
        )
