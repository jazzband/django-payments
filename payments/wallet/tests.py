from mock import MagicMock

from django.http import HttpResponse, HttpResponseForbidden
from django.test import TestCase
import jwt

from . import GoogleWalletProvider

VARIANT = 'wallet'

PAYMENT_TOKEN = "5a4dae68-2715-4b1e-8bb2-2c2dbe9255f6"

SELLER_ID = 'abc123'
SELLER_SECRET = '123abc'

JWT_DATA = {
    "iss": "Google",
    "aud": SELLER_ID,
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
        self.request = MagicMock()
        self.request.POST = {'jwt': jwt.encode(JWT_DATA, SELLER_SECRET)}

    def test_process_data(self):
        """
        GoogleWalletProvider.process_data() returns a correct HTTP response
        """
        provider = GoogleWalletProvider(self.payment, seller_id=SELLER_ID,
                                        seller_secret=SELLER_SECRET)
        response = provider.process_data(self.request)
        self.assertEqual(type(response), HttpResponse)
        self.assertEqual(self.payment.status, 'confirmed')

    def test_incorrect_process_data(self):
        """
        GoogleWalletProvider.process_data() checks POST data
        """
        data = JWT_DATA
        data['aud'] = 'wrong seller id'
        self.request.POST = {'jwt': jwt.encode(data, SELLER_SECRET)}
        provider = GoogleWalletProvider(self.payment, seller_id=SELLER_ID,
                                        seller_secret=SELLER_SECRET)
        response = provider.process_data(self.request)
        self.assertEqual(type(response), HttpResponseForbidden)

    def test_provider_request_payment_token(self):
        provider = GoogleWalletProvider(payment=None, seller_id=SELLER_ID,
                                        seller_secret=SELLER_SECRET)
        token = provider.get_token_from_request(self.request)
        self.assertEqual(token, PAYMENT_TOKEN)

    def test_provider_invalid_request(self):
        self.request.POST = {'jwt': 'wrong jwt data'}
        provider = GoogleWalletProvider(payment=None, seller_id=SELLER_ID,
                                        seller_secret=SELLER_SECRET)
        token = provider.get_token_from_request(self.request)
        self.assertFalse(token)
