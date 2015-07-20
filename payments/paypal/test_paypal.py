from __future__ import unicode_literals
import json
from decimal import Decimal
from unittest import TestCase
from mock import patch, MagicMock

from . import PaypalProvider, PaypalCardProvider
from .. import PurchasedItem, RedirectNeeded, PaymentError
from requests import HTTPError

CLIENT_ID = 'abc123'
PAYMENT_TOKEN = '5a4dae68-2715-4b1e-8bb2-2c2dbe9255f6'
SECRET = '123abc'
VARIANT = 'wallet'

PROCESS_DATA = {
    'name': 'John Doe',
    'number': '371449635398431',
    'expiration_0': '5',
    'expiration_1': '2020',
    'cvv2': '1234'}


class Payment(MagicMock):

    id = 1
    description = 'payment'
    currency = 'USD'
    delivery = Decimal(10)
    status = 'waiting'
    tax = Decimal(10)
    token = PAYMENT_TOKEN
    total = Decimal(100)
    captured_amount = Decimal(0)
    variant = VARIANT
    transaction_id = None
    message = ''
    extra_data = json.dumps({'links': {
        'approval_url': None
    }})

    def change_status(self, status, message=''):
        self.status = status
        self.message = message

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

    def setUp(self):
        self.payment = Payment()
        self.provider = PaypalProvider(secret=SECRET, client_id=CLIENT_ID)

    def test_provider_raises_redirect_needed_on_success(self):
        with patch('requests.post') as mocked_post:
            transaction_id = '1234'
            data = MagicMock()
            data.return_value = {
                'id': transaction_id,
                'token_type': 'test_token_type',
                'access_token': 'test_access_token',
                'links': [
                    {'rel': 'approval_url', 'href': 'http://approval_url.com'}
                ]}
            post = MagicMock()
            post.json = data
            mocked_post.return_value = post
            with self.assertRaises(RedirectNeeded) as exc:
                self.provider.get_form(payment=self.payment)
        self.assertEqual(self.payment.status, 'waiting')
        self.assertEqual(self.payment.captured_amount, Decimal('0'))
        self.assertEqual(self.payment.transaction_id, transaction_id)


class TestPaypalCardProvider(TestCase):

    def setUp(self):
        self.payment = Payment()
        self.provider = PaypalCardProvider(secret=SECRET, client_id=CLIENT_ID)

    def test_provider_raises_redirect_needed_on_success_captured_payment(self):
        with patch('requests.post') as mocked_post:
            transaction_id = '1234'
            data = MagicMock()
            data.return_value = {
                'id': transaction_id,
                'token_type': 'test_token_type',
                'access_token': 'test_access_token'}
            post = MagicMock()
            post.json = data
            mocked_post.return_value = post
            with self.assertRaises(RedirectNeeded) as exc:
                self.provider.get_form(
                    payment=self.payment, data=PROCESS_DATA)
                self.assertEqual(exc.args[0], self.payment.get_success_url())
        self.assertEqual(self.payment.status, 'confirmed')
        self.assertEqual(self.payment.captured_amount, self.payment.total)
        self.assertEqual(self.payment.transaction_id, transaction_id)

    def test_provider_raises_redirect_needed_on_success_preauth_payment(self):
        provider = PaypalCardProvider(
            secret=SECRET, client_id=CLIENT_ID, capture=False)
        with patch('requests.post') as mocked_post:
            transaction_id = '1234'
            data = MagicMock()
            data.return_value = {
                'id': transaction_id,
                'token_type': 'test_token_type',
                'access_token': 'test_access_token'}
            post = MagicMock()
            post.json = data
            mocked_post.return_value = post
            with self.assertRaises(RedirectNeeded) as exc:
                provider.get_form(
                    payment=self.payment, data=PROCESS_DATA)
                self.assertEqual(exc.args[0], self.payment.get_success_url())
        self.assertEqual(self.payment.status, 'preauth')
        self.assertEqual(self.payment.captured_amount, Decimal('0'))
        self.assertEqual(self.payment.transaction_id, transaction_id)

    def test_form_shows_validation_error_message(self):
        with patch('requests.post') as mocked_post:
            error_message = 'error message'
            data = MagicMock()
            data.return_value = {'details': [{'issue': error_message}]}
            post = MagicMock()
            post.json = data
            post.status_code = 400
            mocked_post.side_effect = HTTPError(response=post)
            form = self.provider.get_form(
                payment=self.payment, data=PROCESS_DATA)
        self.assertEqual(self.payment.status, 'error')
        self.assertEqual(form.errors['__all__'][0], error_message)

    def test_form_shows_internal_error_message(self):
        with patch('requests.post') as mocked_post:
            error_message = 'error message'
            data = MagicMock()
            data.return_value = {
                'token_type': 'test_token_type',
                'access_token': 'test_access_token',
                'message': error_message}
            post = MagicMock()
            post.status_code = 400
            post.json = data
            mocked_post.return_value = post
            with self.assertRaises(PaymentError) as exc:
                self.provider.get_form(
                    payment=self.payment, data=PROCESS_DATA)
        self.assertEqual(self.payment.status, 'error')
        self.assertEqual(self.payment.message, error_message)
