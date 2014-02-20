from __future__ import unicode_literals
from decimal import Decimal
import json
from unittest import TestCase

from . import PaypalProvider
from .. import PurchasedItem


CLIENT_ID = 'abc123'
PAYMENT_TOKEN = '5a4dae68-2715-4b1e-8bb2-2c2dbe9255f6'
SECRET = '123abc'
VARIANT = 'wallet'


class Payment(object):

    id = 1
    description = 'payment'
    currency = 'USD'
    delivery = Decimal(10)
    status = 'waiting'
    tax = Decimal(10)
    token = PAYMENT_TOKEN
    total = Decimal(100)
    variant = VARIANT

    def change_status(self, status):
        self.status = status

    def get_failure_url(self):
        return 'http://cancel.com'

    def get_process_url(self):
        return 'http://example.com'

    def get_purchased_items(self):
        return [
            PurchasedItem(
                name='foo', quantity=Decimal('10'), price=Decimal('20'),
                currency='USD', sku='bar')]

    def get_success_url(self):
        return 'http://success.com'


class TestPaypalProvider(TestCase):

    def test_payload_serializable(self):
        payment = Payment()
        provider = PaypalProvider(payment, secret=SECRET, client_id=CLIENT_ID)
        json.dumps(provider.get_product_data())
