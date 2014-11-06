from __future__ import unicode_literals
from decimal import Decimal
from unittest import TestCase

from . import StripeProvider


class Payment(object):

    id = 1
    description = 'payment'
    currency = 'USD'
    delivery = Decimal(10)
    status = 'waiting'
    tax = Decimal(10)
    total = Decimal(100)

    def change_status(self, status):
        self.status = status

    def get_failure_url(self):
        return 'http://cancel.com'

    def get_process_url(self):
        return 'http://example.com'

    def get_purchased_items(self):
        return []

    def save(self):
        return self

    def get_success_url(self):
        return 'http://success.com'


class TestStripeProvider(TestCase):

    def test_form(self):
        payment = Payment()
        provider = StripeProvider(
            payment=payment, name='Example.com store',
            secret_key='123', public_key='abc')
        form = provider.get_form()
        self.assertTrue(
            '<script class="stripe-button" data-amount="10000" data-currency="USD" data-description="payment" data-image="" data-key="abc" data-name="Example.com store" src="https://checkout.stripe.com/checkout.js"></script>' in str(form))
