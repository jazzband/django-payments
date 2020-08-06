from decimal import Decimal
from unittest import TestCase
from django.core import signing
from unittest.mock import patch, MagicMock, Mock

from . import CyberSourceProvider, AUTHENTICATE_REQUIRED, ACCEPTED, \
    TRANSACTION_SETTLED
from .. import PaymentStatus, PurchasedItem, RedirectNeeded

MERCHANT_ID = 'abcd1234'
PASSWORD = '1234abdd1234abcd'
ORG_ID = 'abc'

PROCESS_DATA = {
    'name': 'John Doe',
    'number': '371449635398431',
    'expiration_0': '5',
    'expiration_1': '2023',
    'cvv2': '1234',
    'fingerprint': 'abcd1234'}


class Payment(Mock):
    id = 1
    variant = 'cybersource'
    currency = 'USD'
    total = 100
    status = PaymentStatus.WAITING
    transaction_id = None
    captured_amount = 0
    message = ''

    class attrs(object):
        fingerprint_session_id = 'fake'
        merchant_defined_data = {}

    def get_process_url(self):
        return 'http://example.com'

    def get_failure_url(self):
        return 'http://cancel.com'

    def get_success_url(self):
        return 'http://success.com'

    def change_status(self, status, message=''):
        self.status = status
        self.message = message

    def get_purchased_items(self):
        return [
            PurchasedItem(
                name='foo', quantity=Decimal('10'), price=Decimal('20'),
                currency='USD', sku='bar')]


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
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
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
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
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
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)

    @patch.object(CyberSourceProvider, '_make_request')
    def test_provider_refunds_payment(self, mocked_request):
        self.payment.captured_amount = self.payment.total
        response = MagicMock()
        response.reasonCode = ACCEPTED
        mocked_request.return_value = response
        amount = self.provider.refund(self.payment)
        self.assertEqual(self.payment.total, amount)

    @patch.object(CyberSourceProvider, '_make_request')
    def test_provider_releases_payment(self, mocked_request):
        transaction_id = 123
        response = MagicMock()
        response.requestID = transaction_id
        response.reasonCode = ACCEPTED
        mocked_request.return_value = response
        amount = self.provider.release(self.payment)
        self.assertEqual(self.payment.transaction_id, transaction_id)

    @patch('payments.cybersource.redirect')
    @patch.object(CyberSourceProvider, '_make_request')
    def test_provider_redirects_on_success_captured_payment(
            self, mocked_request, mocked_redirect):
        transaction_id = 1234
        xid = 'abc'
        self.payment.attrs.xid = xid

        response = MagicMock()
        response.requestID = transaction_id
        response.reasonCode = ACCEPTED
        mocked_request.return_value = response

        request = MagicMock()
        request.POST = {'MD': xid}
        request.GET = {'token': signing.dumps({
            'expiration': {'year': 2023, 'month': 9},
            'name': 'John Doe',
            'number': '371449635398431',
            'cvv2': '123'
        })}
        self.provider.process_data(self.payment, request)
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
        self.assertEqual(self.payment.captured_amount, self.payment.total)
        self.assertEqual(self.payment.transaction_id, transaction_id)

    @patch('payments.cybersource.redirect')
    @patch.object(CyberSourceProvider, '_make_request')
    @patch('payments.cybersource.suds.client.Client', new=MagicMock())
    def test_provider_redirects_on_success_preauth_payment(
            self, mocked_request, mocked_redirect):
        provider = CyberSourceProvider(
            merchant_id=MERCHANT_ID, password=PASSWORD, org_id=ORG_ID,
            capture=False)
        transaction_id = 1234
        xid = 'abc'
        self.payment.attrs.xid = xid

        response = MagicMock()
        response.requestID = transaction_id
        response.reasonCode = ACCEPTED
        mocked_request.return_value = response

        request = MagicMock()
        request.POST = {'MD': xid}
        request.GET = {'token': signing.dumps({
            'expiration': {'year': 2023, 'month': 9},
            'name': 'John Doe',
            'number': '371449635398431',
            'cvv2': '123'
        })}
        provider.process_data(self.payment, request)
        self.assertEqual(self.payment.status, PaymentStatus.PREAUTH)
        self.assertEqual(self.payment.captured_amount, 0)
        self.assertEqual(self.payment.transaction_id, transaction_id)

    @patch('payments.cybersource.redirect')
    @patch.object(CyberSourceProvider, '_make_request')
    @patch('payments.cybersource.suds.client.Client', new=MagicMock())
    def test_provider_redirects_on_failure(
            self, mocked_request, mocked_redirect):
        transaction_id = 1234
        xid = 'abc'
        self.payment.attrs.xid = xid

        response = MagicMock()
        response.requestID = transaction_id
        response.reasonCode = 'test code'
        mocked_request.return_value = response

        request = MagicMock()
        request.POST = {'MD': xid}
        request.GET = {'token': signing.dumps({
            'expiration': {'year': 2023, 'month': 9},
            'name': 'John Doe',
            'number': '371449635398431',
            'cvv2': '123'
        })}
        self.provider.process_data(self.payment, request)
        self.assertEqual(self.payment.status, PaymentStatus.ERROR)
        self.assertEqual(self.payment.captured_amount, 0)
        self.assertEqual(self.payment.transaction_id, transaction_id)
