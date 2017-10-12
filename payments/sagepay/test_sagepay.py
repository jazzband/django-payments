from __future__ import unicode_literals
from unittest import TestCase
try:
    from unittest.mock import patch, MagicMock
except ImportError:
    from mock import patch, MagicMock

from . import SagepayProvider
from .. import PaymentStatus
from ..testcommon import create_test_payment


VENDOR = 'abcd1234'
ENCRYPTION_KEY = '1234abdd1234abcd'


Payment = create_test_payment()


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
            self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
            self.assertEqual(self.payment.captured_amount, self.payment.total)

    @patch('payments.sagepay.redirect')
    def test_provider_raises_redirect_needed_on_failure(self, mocked_redirect):
        data = {'Status': ''}
        data = "&".join(u"%s=%s" % kv for kv in data.items())
        with patch.object(SagepayProvider, 'aes_dec', return_value=data):
            self.provider.process_data(self.payment, MagicMock())
            self.assertEqual(self.payment.status, PaymentStatus.REJECTED)
            self.assertEqual(self.payment.captured_amount, 0)

    def test_provider_encrypts_data(self):
        data = self.provider.get_hidden_fields(self.payment)
        decrypted_data = self.provider.aes_dec(data['Crypt'])
        self.assertIn(self.payment.billing_first_name, str(decrypted_data))

    def test_encrypt_method_returns_valid_data(self):
        encrypted = self.provider.aes_enc('mirumee')
        self.assertEqual(encrypted, b'@e63c293672f50b9c8e291831facb4e4f')
