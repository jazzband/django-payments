
import simplejson as json

from unittest import TestCase
try:
    from unittest.mock import MagicMock, patch
except ImportError:
    from mock import MagicMock, patch

from . import PaydirektProvider
from .. import FraudStatus, PaymentError, PaymentStatus, RedirectNeeded
from ..testcommon import create_test_payment

VARIANT = 'paydirekt'
API_KEY = '5a4dae68-2715-4b1e-8bb2-2c2dbe9255f6'
SECRET = '123abc'

PROCESS_DATA = {
  "checkoutId" : "64e0bd1f-c3a3-47e1-aaff-75e690c062f8",
  "merchantOrderReferenceNumber" : "order-A12223412",
  "checkoutStatus" : "APPROVED"
}

Payment = create_test_payment(variant=VARIANT, currency='EUR')


class TestPaydirektProvider(TestCase):

    def setUp(self):
        self.payment = Payment()
        self.provider = PaydirektProvider(API_KEY, SECRET)

    def test_process_data_works(self):
        request = MagicMock()
        request.body = json.dumps(PROCESS_DATA)
        response = self.provider.process_data(self.payment, request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
