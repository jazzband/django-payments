from __future__ import unicode_literals

import hashlib
import json
from decimal import Decimal
from unittest import TestCase
try:
    from unittest.mock import patch, MagicMock
except ImportError:
    from mock import patch, MagicMock

from django.http import HttpResponse, HttpResponseForbidden

from .. import PaymentStatus
from . import CoinbaseProvider
from ..testcommon import create_test_payment

PAYMENT_TOKEN = '5a4dae68-2715-4b1e-8bb2-2c2dbe9255f6'
KEY = 'abc123'
SECRET = '123abc'
VARIANT = 'coinbase'

COINBASE_REQUEST = {
    'order': {
        'transaction': {'id': '123456'},
        'custom': hashlib.md5(('coinbase-%s-%s' % (
            PAYMENT_TOKEN, KEY)).encode('utf-8')).hexdigest()}}


Payment = create_test_payment(variant=VARIANT, token=PAYMENT_TOKEN, description='payment', currency='BTC', total=Decimal(100))

class TestCoinbaseProvider(TestCase):

    def setUp(self):
        self.payment = Payment()
        self.provider = CoinbaseProvider(key=KEY, secret=SECRET)

    def test_process_data(self):
        """
        CoinbaseProvider.process_data() returns a correct HTTP response
        """
        request = MagicMock()
        request.body = json.dumps(COINBASE_REQUEST)
        response = self.provider.process_data(self.payment, request)
        self.assertEqual(type(response), HttpResponse)
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)

    def test_incorrect_custom_token_process_data(self):
        """
        CoinbaseProvider.process_data() checks request custom token
        """
        data = dict(COINBASE_REQUEST)
        data.update({'order': {'custom': 'fake'}})
        request = MagicMock()
        request.body = json.dumps(data)
        response = self.provider.process_data(self.payment, request)
        self.assertEqual(type(response), HttpResponseForbidden)

    def test_incorrect_data_process_data(self):
        """
        CoinbaseProvider.process_data() checks request body
        """
        request = MagicMock()
        request.POST = {'id': '1234'}
        response = self.provider.process_data(self.payment, request)
        self.assertEqual(type(response), HttpResponseForbidden)

    @patch('time.time')
    @patch('requests.post')
    def test_provider_returns_checkout_url(self, mocked_post, mocked_time):
        code = '123abc'
        signature = '21d476eff7b2e6cccdfe6deb0c097ba638d5de7e775b303e' \
                    '4fdb2f8bfeff72e2'
        url = 'https://sandbox.coinbase.com/checkouts/%s' % code
        post = MagicMock()
        post.json = MagicMock(return_value={'button': {'code': code}})
        post.status_code = 200
        mocked_post.return_value = post
        mocked_time.return_value = 1

        form = self.provider.get_form(self.payment)
        self.assertEqual(form.action, url)
        self.assertEqual(
            mocked_post.call_args[1]['headers']['ACCESS_SIGNATURE'], signature)
