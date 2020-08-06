from unittest import TestCase
from unittest.mock import patch, MagicMock, Mock
import json

from . import SofortProvider
from .. import PaymentStatus, RedirectNeeded

SECRET = 'abcd1234'
CLIENT_ID = '1234'
PROJECT_ID = 'abcd'


class Payment(Mock):
    id = 1
    variant = 'sagepay'
    currency = 'USD'
    total = 100
    status = PaymentStatus.WAITING
    transaction_id = None
    captured_amount = 0
    billing_first_name = 'John'

    def get_process_url(self):
        return 'http://example.com'

    def get_failure_url(self):
        return 'http://cancel.com'

    def get_success_url(self):
        return 'http://success.com'

    def change_status(self, status):
        self.status = status


class TestSofortProvider(TestCase):

    def setUp(self):
        self.payment = Payment()
        self.provider = SofortProvider(
            id=CLIENT_ID, project_id=PROJECT_ID, key=SECRET)

    @patch('xmltodict.parse')
    @patch('requests.post')
    def test_provider_raises_redirect_needed_on_success(
            self, mocked_post, mocked_parser):
        response = MagicMock()
        response.status_code = 200
        mocked_post.return_value = response
        mocked_parser.return_value = {
            'new_transaction': {
                'payment_url': 'http://payment.com'}}
        with self.assertRaises(RedirectNeeded) as exc:
            self.provider.get_form(self.payment)

    @patch('xmltodict.parse')
    @patch('requests.post')
    @patch('payments.sofort.redirect')
    def test_provider_redirects_on_success(
            self, mocked_redirect, mocked_post, mocked_parser):
        transaction_id = '1234'
        request = MagicMock()
        request.GET = {'trans': transaction_id}
        mocked_parser.return_value = {
            'transactions': {
                'transaction_details': {
                    'status': 'ok',
                    'sender': {
                        'holder': 'John Doe',
                        'country_code': 'EN'}}}}
        self.provider.process_data(self.payment, request)
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
        self.assertEqual(self.payment.captured_amount, self.payment.total)
        self.assertEqual(self.payment.transaction_id, transaction_id)

    @patch('xmltodict.parse')
    @patch('requests.post')
    @patch('payments.sofort.redirect')
    def test_provider_redirects_on_failure(
            self, mocked_redirect, mocked_post, mocked_parser):
        transaction_id = '1234'
        request = MagicMock()
        request.GET = {'trans': transaction_id}
        mocked_parser.return_value = {}
        self.provider.process_data(self.payment, request)
        self.assertEqual(self.payment.status, PaymentStatus.REJECTED)
        self.assertEqual(self.payment.captured_amount, 0)
        self.assertEqual(self.payment.transaction_id, transaction_id)

    @patch('xmltodict.parse')
    @patch('requests.post')
    def test_provider_refunds_payment(self, mocked_post, mocked_parser):
        self.payment.extra_data = json.dumps({
            'transactions': {
                'transaction_details': {
                    'status': 'ok',
                    'sender': {
                        'holder': 'John Doe',
                        'country_code': 'EN',
                        'bic': '1234',
                        'iban': 'abcd'}}}})
        mocked_parser.return_value = {}
        self.provider.refund(self.payment)
        self.assertEqual(self.payment.status, PaymentStatus.REFUNDED)
