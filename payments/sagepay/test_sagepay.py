from __future__ import unicode_literals
from unittest import TestCase
from mock import patch, MagicMock

from . import SagepayProvider


VENDOR = 'abcd1234'
ENCRYPTION_KEY = '1234abdd1234abcd'


class Payment(MagicMock):

    id = 1
    variant = 'sagepay'
    currency = 'USD'
    total = 100
    status = 'waiting'
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


class TestSagepayProvider(TestCase):

    def setUp(self):
        self.payment = Payment()
        self.provider = SagepayProvider(
            vendor=VENDOR, encryption_key=ENCRYPTION_KEY)

    @patch('payments.sagepay.redirect')
    def test_provider_raises_redirect_needed_on_success(self, mocked_redirect):
        data = {'Status': 'OK'}
        data = "&".join(u"%s=%s" % kv for kv in data.items())
        with patch.object(SagepayProvider, 'aes_dec', return_value=data):
            self.provider.process_data(self.payment, MagicMock())
            self.assertEqual(self.payment.status, 'confirmed')
            self.assertEqual(self.payment.captured_amount, self.payment.total)

    @patch('payments.sagepay.redirect')
    def test_provider_raises_redirect_needed_on_failure(self, mocked_redirect):
        data = {'Status': ''}
        data = "&".join(u"%s=%s" % kv for kv in data.items())
        with patch.object(SagepayProvider, 'aes_dec', return_value=data):
            self.provider.process_data(self.payment, MagicMock())
            self.assertEqual(self.payment.status, 'rejected')
            self.assertEqual(self.payment.captured_amount, 0)

    def test_provider_encrypts_data(self):
        data = self.provider.get_hidden_fields(self.payment)
        decrypted_data = self.provider.aes_dec(data['Crypt'])
        self.assertIn(self.payment.billing_first_name, str(decrypted_data))
