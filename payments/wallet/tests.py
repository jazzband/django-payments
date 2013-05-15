from mock import MagicMock

from django.http import HttpResponse, HttpResponseForbidden
from django.test import TestCase
import jwt

from . import GoogleWalletProvider

VARIANT = 'wallet'

PAYMENT_TOKEN = "5a4dae68-2715-4b1e-8bb2-2c2dbe9255f6"

MERCHANT_ID = 'abc123'
MERCHANT_SECRET = '123abc'

JWT_DATA = {
    "iss": "Google",
    "aud": MERCHANT_ID,
    "typ": "google/payments/inapp/item/v1/postback/buy",
    "iat": "1309988959",
    "exp": "1409988959",
    "request": {
        "name": "Test Order #12",
        "price": "22.50",
        "currencyCode": "USD",
        "sellerData": PAYMENT_TOKEN
    },
    "response": {
        "orderId": "1234567890"
    }
}


class Payment(MagicMock):

    id = 1
    variant = VARIANT
    currency = 'USD'
    total = 100
    token = PAYMENT_TOKEN
    status = 'waiting'

    def change_status(self, status):
        self.status = status

    def get_failure_url(self):
        return 'http://cancel.com'

    def get_success_url(self):
        return 'http://success.com'


class TestGoogleWalletProvider(TestCase):

    def setUp(self):
        self.payment = Payment()

    def test_process_data(self):
        """GoogleWalletProvider.process_data() returns a correct HTTP response"""
        request = MagicMock()
        request.POST = {'jwt': jwt.encode(JWT_DATA, MERCHANT_SECRET)}
        provider = GoogleWalletProvider(self.payment, merchant_id=MERCHANT_ID, merchant_secret=MERCHANT_SECRET)
        response = provider.process_data(request)
        self.assertEqual(type(response), HttpResponse)
        self.assertEqual(self.payment.status, 'confirmed')

    def test_uncorrect_process_data(self):
        """GoogleWalletProvider.process_data() checks POST data"""
        request = MagicMock()
        data = JWT_DATA
        data['aud'] = 'wrong merchant id'
        request.POST = {'jwt': jwt.encode(data, MERCHANT_SECRET)}
        provider = GoogleWalletProvider(self.payment, merchant_id=MERCHANT_ID, merchant_secret=MERCHANT_SECRET)
        response = provider.process_data(request)
        self.assertEqual(type(response), HttpResponseForbidden)