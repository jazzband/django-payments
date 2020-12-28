from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

from . import AuthorizeNetProvider
from .. import PaymentStatus
from .. import RedirectNeeded


LOGIN_ID = 'abcd1234'
TRANSACTION_KEY = '1234abdd'

PROCESS_DATA = {
    'number': '4007000000027',
    'expiration_0': '5',
    'expiration_1': '2023',
    'cvv2': '123'}

STATUS_CONFIRMED = '1'


class Payment(Mock):
    id = 1
    variant = 'authorizenet'
    currency = 'USD'
    total = 100
    status = PaymentStatus.WAITING
    transaction_id = None
    captured_amount = 0

    def get_process_url(self):
        return 'http://example.com'

    def get_failure_url(self):
        return 'http://cancel.com'

    def get_success_url(self):
        return 'http://success.com'

    def change_status(self, status):
        self.status = status


class TestAuthorizeNetProvider(TestCase):

    def setUp(self):
        self.payment = Payment()

    def test_provider_redirects_to_success_on_payment_success(self):
        provider = AuthorizeNetProvider(
            login_id=LOGIN_ID, transaction_key=TRANSACTION_KEY)

        response_data = [
            STATUS_CONFIRMED,
            '',
            '',
            'This transaction has been approved.',
            '',
            '',
            '1234']

        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.text = '|'.join(response_data)
            mocked_post.return_value = post
            with self.assertRaises(RedirectNeeded) as exc:
                provider.get_form(self.payment, data=PROCESS_DATA)
                self.assertEqual(exc.args[0], self.payment.get_success_url())
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
        self.assertEqual(self.payment.captured_amount, self.payment.total)

    def test_provider_shows_validation_error_message(self):
        provider = AuthorizeNetProvider(
            login_id=LOGIN_ID, transaction_key=TRANSACTION_KEY)

        error_msg = 'The merchant does not accept this type of credit card.'
        response_data = [
            '',
            '',
            '',
            error_msg,
            '',
            '',
            '1234']

        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.ok = False
            post.text = '|'.join(response_data)
            mocked_post.return_value = post
            form = provider.get_form(self.payment, data=PROCESS_DATA)
            self.assertEqual(form.errors['__all__'][0], error_msg)
        self.assertEqual(self.payment.status, PaymentStatus.ERROR)
        self.assertEqual(self.payment.captured_amount, 0)
