from __future__ import unicode_literals
from unittest import TestCase
from mock import patch, MagicMock

from . import CyberSourceProvider, AUTHENTICATE_REQUIRED, ACCEPTED, \
    TRANSACTION_SETTLED
from payments import RedirectNeeded, ExternalPostNeeded

MERCHANT_ID = 'abcd1234'
PASSWORD = '1234abdd1234abcd'
ORG_ID = 'abc'

PROCESS_DATA = {
    'name': 'John Doe',
    'number': '371449635398431',
    'expiration_0': '5',
    'expiration_1': '2020',
    'cvv2': '1234',
    'fingerprint': 'abcd1234'}


class Payment(MagicMock):

    id = 1
    variant = 'cybersource'
    currency = 'USD'
    total = 100
    status = 'waiting'
    transaction_id = None
    captured_amount = 0
    message = ''

    def get_process_url(self):
        return 'http://example.com'

    def get_failure_url(self):
        return 'http://cancel.com'

    def get_success_url(self):
        return 'http://success.com'

    def change_status(self, status, message=''):
        self.status = status
        self.message = message


class TestCybersourceProvider(TestCase):

    @patch('payments.cybersource.suds.client.Client', new=MagicMock())
    def setUp(self):
        self.payment = Payment()
        self.provider = CyberSourceProvider(
            merchant_id=MERCHANT_ID, password=PASSWORD, org_id=ORG_ID)

    @patch.object(CyberSourceProvider, '_make_request')
    def test_provider_raises_redirect_needed_on_success(self, mocked_request):
        transaction_id = 1234
        response = MagicMock()
        response.requestID = transaction_id
        response.reasonCode = 100
        mocked_request.return_value = response
        with self.assertRaises(RedirectNeeded) as exc:
            self.provider.get_form(
                payment=self.payment, data=PROCESS_DATA)
        self.assertEqual(self.payment.status, 'confirmed')
        self.assertEqual(self.payment.captured_amount, self.payment.total)
        self.assertEqual(self.payment.transaction_id, transaction_id)

    @patch.object(CyberSourceProvider, '_make_request')
    def test_provider_returns_form_on_3d_secure(
            self, mocked_request):
        response = MagicMock()
        response.reasonCode = AUTHENTICATE_REQUIRED
        mocked_request.return_value = response
        form = self.provider.get_form(
            payment=self.payment, data=PROCESS_DATA)
        self.assertEqual(self.payment.status, 'waiting')
        self.assertIn('PaReq', form.fields)

    @patch.object(CyberSourceProvider, '_make_request')
    def test_provider_shows_validation_error_message_response(
            self, mocked_request):
        error_message = 'The card you are trying to use was reported ' \
                        'as lost or stolen.'
        error_code = 205
        response = MagicMock()
        response.reasonCode = error_code
        mocked_request.return_value = response
        form = self.provider.get_form(
            payment=self.payment, data=PROCESS_DATA)
        self.assertEqual(form.errors['__all__'][0], error_message)

    def test_provider_shows_validation_error_message_duplicate(self):
        self.payment.transaction_id = 1
        error_message = 'This payment has already been processed.'
        form = self.provider.get_form(
            payment=self.payment, data=PROCESS_DATA)
        self.assertEqual(form.errors['__all__'][0], error_message)

    @patch.object(CyberSourceProvider, '_make_request')
    def test_provider_captures_payment(self, mocked_request):
        transaction_id = 1234
        response = MagicMock()
        response.requestID = transaction_id
        response.reasonCode = TRANSACTION_SETTLED
        mocked_request.return_value = response
        self.provider.capture(self.payment)
        self.assertEqual(self.payment.status, 'confirmed')
