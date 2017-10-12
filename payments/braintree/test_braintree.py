from __future__ import unicode_literals
from unittest import TestCase
try:
    from unittest.mock import patch, MagicMock
except ImportError:
    from mock import patch, MagicMock

from . import BraintreeProvider
from .. import PaymentStatus, RedirectNeeded
from ..testcommon import create_test_payment


MERCHANT_ID = 'test11'
PUBLIC_KEY = 'abcd1234'
PRIVATE_KEY = '1234abcd'

PROCESS_DATA = {
    'name': 'John Doe',
    'number': '371449635398431',
    'expiration_0': '5',
    'expiration_1': '2020',
    'cvv2': '1234'}


Payment = create_test_payment()


class TestBraintreeProvider(TestCase):

    def setUp(self):
        self.payment = Payment()

    def test_provider_redirects_to_success_on_payment_success(self):
        provider = BraintreeProvider(MERCHANT_ID, PUBLIC_KEY, PRIVATE_KEY)
        transaction_id = '12345'
        with patch('braintree.Transaction'):
            with patch('braintree.Transaction.sale') as mocked_sale:
                sale = MagicMock()
                sale.is_success = True
                sale.transaction.id = transaction_id
                mocked_sale.return_value = sale
                with self.assertRaises(RedirectNeeded) as exc:
                    provider.get_form(self.payment, data=PROCESS_DATA)
                    url = exc.args[0]
                    self.assertEqual(url, self.payment.get_success_url())
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
        self.assertEqual(self.payment.captured_amount, self.payment.total)
        self.assertEqual(self.payment.transaction_id, transaction_id)

    def test_provider_shows_validation_error_message(self):
        provider = BraintreeProvider(MERCHANT_ID, PUBLIC_KEY, PRIVATE_KEY)
        error_msg = 'error message'
        with patch('braintree.Transaction'):
            with patch('braintree.Transaction.sale') as mocked_sale:
                sale = MagicMock()
                sale.is_success = False
                sale.message = error_msg
                mocked_sale.return_value = sale
                form = provider.get_form(self.payment, data=PROCESS_DATA)
                self.assertEqual(form.errors['__all__'][0], error_msg)
        self.assertEqual(self.payment.status, PaymentStatus.ERROR)
        self.assertEqual(self.payment.captured_amount, 0)
