from mock import MagicMock
import hashlib

from django.http import HttpResponse, HttpResponseForbidden
from django.test import TestCase

from .forms import ACCEPTED
from . import DotpayProvider

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
    md5.update(key)
    key_hash = md5.hexdigest()
    post['md5'] = key_hash
    return post


class Payment(MagicMock):

    id = 1
    variant = VARIANT
    currency = 'USD'
    total = 100

    def get_failure_url(self):
        return 'http://cancel.com'

    def get_success_url(self):
        return 'http://success.com'


class TestDotpayProvider(TestCase):

    def setUp(self):
        self.payment = Payment()

    def test_get_hidden_fields(self):
        """DotpayProvider.get_hidden_fields() returns a dictionary"""
        provider = DotpayProvider(self.payment, seller_id='123', pin=PIN)
        self.assertEqual(type(provider.get_hidden_fields()), dict)

    def test_process_data(self):
        """DotpayProvider.process_data() returns a correct HTTP response"""
        request = MagicMock()
        request.POST = get_post_with_md5(PROCESS_POST)
        provider = DotpayProvider(self.payment, seller_id='123', pin=PIN)
        response = provider.process_data(request)
        self.assertEqual(type(response), HttpResponse)

    def test_uncorrect_process_data(self):
        """DotpayProvider.process_data() checks POST signature"""
        request = MagicMock()
        request.POST = PROCESS_POST
        provider = DotpayProvider(self.payment, seller_id='123', pin=PIN)
        response = provider.process_data(request)
        self.assertEqual(type(response), HttpResponseForbidden)
