from __future__ import unicode_literals

import hashlib
import json
from decimal import Decimal
from unittest import TestCase

from django.http import HttpResponse, HttpResponseForbidden
from mock import MagicMock

from . import CoinbaseProvider


PAYMENT_TOKEN = '5a4dae68-2715-4b1e-8bb2-2c2dbe9255f6'
KEY = 'abc123'
SECRET = '123abc'
VARIANT = 'coinbase'

COINBASE_REQUEST = {
    'order': {
        'transaction': {'id': '123456'},
        'custom': hashlib.md5(('coinbase-%s-%s' % (
            PAYMENT_TOKEN, KEY)).encode('utf-8')).hexdigest()}}


class Payment(object):

    id = 1
    description = 'payment'
    currency = 'BTC'
    total = Decimal(100)
    status = 'waiting'
    token = PAYMENT_TOKEN
    variant = VARIANT

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


class TestCoinbaseProvider(TestCase):

    def test_process_data(self):
        """
        CoinbaseProvider.process_data() returns a correct HTTP response
        """
        payment = Payment()
        request = MagicMock()
        request.body = json.dumps(COINBASE_REQUEST)
        provider = CoinbaseProvider(payment, key=KEY, secret=SECRET)
        response = provider.process_data(request)
        self.assertEqual(type(response), HttpResponse)
        self.assertEqual(payment.status, 'confirmed')

    def test_incorrect_custom_token_process_data(self):
        """
        CoinbaseProvider.process_data() checks request custom token
        """
        data = dict(COINBASE_REQUEST)
        data.update({'order': {'custom': 'fake'}})
        payment = Payment()
        request = MagicMock()
        request.body = json.dumps(data)
        provider = CoinbaseProvider(payment, key=KEY, secret=SECRET)
        response = provider.process_data(request)
        self.assertEqual(type(response), HttpResponseForbidden)

    def test_incorrect_data_process_data(self):
        """
        CoinbaseProvider.process_data() checks request body
        """
        payment = Payment()
        request = MagicMock()
        request.POST = {'id': '1234'}
        provider = CoinbaseProvider(payment, key=KEY, secret=SECRET)
        response = provider.process_data(request)
        self.assertEqual(type(response), HttpResponseForbidden)
