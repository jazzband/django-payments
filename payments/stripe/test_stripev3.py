import json
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch

from .. import PaymentError
from .. import PaymentStatus
from .. import RedirectNeeded
from . import StripeProviderV3

# Secret key from https://stripe.com/docs/api/authentication
API_KEY = "sk_test_4eC39HqLyjWDarjtT1zdp7dc"
API_KEY_BAD = "aaaaaaa123"


class payment_attrs:
    session = dict


class Payment(Mock):
    id = 1
    description = "payment"
    currency = "USD"
    delivery = 10
    status = PaymentStatus.WAITING
    message = None
    tax = 10
    total = 100
    captured_amount = 0
    transaction_id = None
    billing_email = "john@doe.com"
    attrs = payment_attrs()

    def change_status(self, status, message=""):
        self.status = status
        self.message = message

    def get_failure_url(self):
        return "http://cancel.com"

    def get_process_url(self):
        return "http://example.com"

    def get_purchased_items(self):
        return []

    def get_success_url(self):
        return "http://success.com"


class TestStripeProviderV3(TestCase):
    def test_provider_create_session_success(self):
        payment = Payment()
        provider = StripeProviderV3(api_key=API_KEY)
        return_value = {
            "id": "cs_test_...",
            "url": "https://checkout.stripe.com/c/pay/cs_test_...",
            "status": "open",
            "payment_status": "unpaid",
            "payment_intent": "pi_...",
        }
        with patch("stripe.checkout.Session.create", return_value=return_value):
            with self.assertRaises(RedirectNeeded):
                provider.get_form(payment)
                self.assertTrue("url" in payment.attrs.session)
                self.assertTrue("id" in payment.attrs.session)
        self.assertEqual(payment.status, PaymentStatus.WAITING)

    def test_provider_create_session_failure(self):
        payment = Payment()
        provider = StripeProviderV3(api_key=API_KEY)
        return_value = {
            "status": "open",
            "payment_status": "unpaid",
            "payment_intent": "pi_...",
        }
        with patch(
            "stripe.checkout.Session.create", return_value=return_value
        ) as f_session:
            f_session.side_effect = PaymentError("Error")
            with self.assertRaises(PaymentError):
                provider.get_form(payment)

            self.assertEqual(payment.status, PaymentStatus.ERROR)

    def test_provider_create_session_failure_no_url(self):
        payment = Payment()
        provider = StripeProviderV3(api_key=API_KEY)
        return_value = {
            "status": "open",
            "payment_status": "unpaid",
            "payment_intent": "pi_...",
        }
        with patch("stripe.checkout.Session.create", return_value=return_value):
            with self.assertRaises(PaymentError):
                provider.get_form(payment)

            self.assertFalse("url" in payment.attrs.session)
            self.assertFalse("id" in payment.attrs.session)

    def test_provider_status(self):
        payment = Payment()
        provider = StripeProviderV3(api_key=API_KEY)

        class return_value:
            payment_status = "paid"

        with patch("stripe.checkout.Session.retrieve", return_value=return_value):
            provider.status(payment)

    def test_provider_refund_failure_bad_status(self):
        payment = Payment()
        provider = StripeProviderV3(api_key=API_KEY)
        with self.assertRaises(PaymentError):
            provider.refund(payment)
