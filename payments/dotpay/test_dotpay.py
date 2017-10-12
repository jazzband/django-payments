from __future__ import unicode_literals
import hashlib
from unittest import TestCase

from django.http import HttpResponse, HttpResponseForbidden
try:
    from unittest.mock import MagicMock
except ImportError:
    from mock import MagicMock

from .. import PaymentStatus
from .forms import ACCEPTED, REJECTED
from . import DotpayProvider
from ..testcommon import create_test_payment

VARIANT = 'dotpay'
PIN = '123'
PROCESS_POST = {
    'status': 'OK',
    'id': '111',
    'control': '1',
    't_id': 't111',
    'amount': '100.0',
    'email': 'chf@o2.pl',
    't_status': str(ACCEPTED),
    'description': 'description',
    'md5': '?'}


def get_post_with_md5(post):
    post = post.copy()
    key_vars = (
        PIN,
        post['id'],
        post['control'],
        post['t_id'],
        post['amount'],
        post.get('email', ''),
        '',  # service
        '',  # code
        '',  # username
        '',  # password
        post['t_status'])
    key = ':'.join(key_vars)
    md5 = hashlib.md5()
    md5.update(key.encode('utf-8'))
    key_hash = md5.hexdigest()
    post['md5'] = key_hash
    return post


Payment = create_test_payment(variant=VARIANT, id=1, currency='USD')


class TestDotpayProvider(TestCase):

    def setUp(self):
        self.payment = Payment()

    def test_get_hidden_fields(self):
        """DotpayProvider.get_hidden_fields() returns a dictionary"""
        provider = DotpayProvider(seller_id='123', pin=PIN)
        self.assertEqual(type(provider.get_hidden_fields(self.payment)), dict)

    def test_process_data_payment_accepted(self):
        """DotpayProvider.process_data() returns a correct HTTP response"""
        request = MagicMock()
        request.POST = get_post_with_md5(PROCESS_POST)
        params = {
            'seller_id': 123,
            'pin': PIN,
            'endpoint': 'test.endpoint.com',
            'channel': 1,
            'lang': 'en',
            'lock': True}
        provider = DotpayProvider(**params)
        response = provider.process_data(self.payment, request)
        self.assertEqual(type(response), HttpResponse)
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)

    def test_process_data_payment_rejected(self):
        """DotpayProvider.process_data() returns a correct HTTP response"""
        data = dict(PROCESS_POST)
        data.update({'t_status': str(REJECTED)})
        request = MagicMock()
        request.POST = get_post_with_md5(data)
        params = {
            'seller_id': 123,
            'pin': PIN,
            'endpoint': 'test.endpoint.com',
            'channel': 1,
            'lang': 'en',
            'lock': True}
        provider = DotpayProvider(**params)
        response = provider.process_data(self.payment, request)
        self.assertEqual(type(response), HttpResponse)
        self.assertEqual(self.payment.status, PaymentStatus.REJECTED)

    def test_incorrect_process_data(self):
        """DotpayProvider.process_data() checks POST signature"""
        request = MagicMock()
        request.POST = PROCESS_POST
        provider = DotpayProvider(seller_id='123', pin=PIN)
        response = provider.process_data(self.payment, request)
        self.assertEqual(type(response), HttpResponseForbidden)
