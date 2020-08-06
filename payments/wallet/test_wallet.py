import time
from decimal import Decimal
from unittest import TestCase

from django.http import HttpResponse, HttpResponseForbidden
import jwt
from unittest.mock import MagicMock

from .. import PaymentStatus
from . import GoogleWalletProvider

PAYMENT_TOKEN = '5a4dae68-2715-4b1e-8bb2-2c2dbe9255f6'
SELLER_ID = 'abc123'
SELLER_SECRET = '123abc'
VARIANT = 'wallet'


JWT_DATA = {
    'iss': 'Google',
    'aud': SELLER_ID,
    'typ': 'google/payments/inapp/item/v1/postback/buy',
    'iat': int(time.time()),
    'exp': int(time.time() + 3600),
    'request': {
        'name': 'Test Order #12',
        'price': '22.50',
        'currencyCode': 'USD',
        'sellerData': PAYMENT_TOKEN},
    'response': {
        'orderId': '1234567890'}}


class Payment:

    id = 1
    description = 'payment'
    currency = 'USD'
    delivery = Decimal(10)
    status = PaymentStatus.WAITING
    tax = Decimal(10)
    token = PAYMENT_TOKEN
    total = Decimal(100)
    variant = VARIANT

    def change_status(self, status):
        self.status = status

    def get_failure_url(self):
        return 'http://cancel.com'

    def get_process_url(self):
        return 'http://example.com'

    def get_purchased_items(self):
        return []

    def save(self):
        return self

    def get_success_url(self):
        return 'http://success.com'


class TestGoogleWalletProvider(TestCase):

    def test_process_data(self):
        """
        GoogleWalletProvider.process_data() returns a correct HTTP response
        """
        payment = Payment()
        request = MagicMock()
        request.POST = {'jwt': jwt.encode(JWT_DATA, SELLER_SECRET).decode()}
        provider = GoogleWalletProvider(
            seller_id=SELLER_ID, seller_secret=SELLER_SECRET)
        response = provider.process_data(payment, request)
        self.assertEqual(type(response), HttpResponse)
        self.assertEqual(payment.status, PaymentStatus.CONFIRMED)

    def test_incorrect_process_data(self):
        """
        GoogleWalletProvider.process_data() checks POST data
        """
        data = dict(JWT_DATA, aud='wrong seller id')
        payment = Payment()
        request = MagicMock()
        payload = jwt.encode(data, SELLER_SECRET).decode()
        request.POST = {'jwt': payload}
        provider = GoogleWalletProvider(
            seller_id=SELLER_ID, seller_secret=SELLER_SECRET)
        response = provider.process_data(payment, request)
        self.assertEqual(type(response), HttpResponseForbidden)

    def test_provider_request_payment_token(self):
        request = MagicMock()
        request.POST = {'jwt': jwt.encode(JWT_DATA, SELLER_SECRET).decode()}
        provider = GoogleWalletProvider(
            seller_id=SELLER_ID, seller_secret=SELLER_SECRET)
        token = provider.get_token_from_request(None, request)
        self.assertEqual(token, PAYMENT_TOKEN)

    def test_provider_invalid_request(self):
        request = MagicMock()
        request.POST = {'jwt': 'wrong jwt data'}
        provider = GoogleWalletProvider(
            seller_id=SELLER_ID, seller_secret=SELLER_SECRET)
        token = provider.get_token_from_request(None, request)
        self.assertFalse(token)

    def test_jwt_encoder(self):
        payment = Payment()
        provider = GoogleWalletProvider(
            seller_id=SELLER_ID, seller_secret=SELLER_SECRET)
        payload = provider.get_jwt_data(payment)
        data = jwt.decode(
            payload, SELLER_SECRET, audience='Google', issuer=SELLER_ID)
        self.assertEqual(data['request']['price'], '100')

    def test_form_contains_additional_media(self):
        payment = Payment()
        library = 'http://example.com/checkout/lib.js'
        provider = GoogleWalletProvider(
            seller_id=SELLER_ID, seller_secret=SELLER_SECRET, library=library)
        form = provider.get_form(payment)
        self.assertIn(library, str(form.media))
