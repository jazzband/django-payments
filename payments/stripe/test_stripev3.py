from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch

import stripe

from .. import PaymentStatus
from .. import PaymentError
from .. import RedirectNeeded
from . import StripeProviderV3

# Secret key from https://stripe.com/docs/api/authentication
SECRET_KEY = "sk_test_4eC39HqLyjWDarjtT1zdp7dc"
SECRET_KEY_BAD = "aaaaaaa123"


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


@contextmanager
def mock_stripe_Session_create(error_msg=None):
    json_body = {"error": {"session": "session_id"}}
    with patch("stripe.checkout.Session.create") as mocked_session_create:
        if error_msg:
            mocked_session_create.side_effect = stripe.error.StripeError(
                error_msg, code=None, json_body=json_body
            )
        else:
            mocked_session_create.side_effect = lambda **kwargs: {}
        yield mocked_session_create


class TestStripeProviderV3(TestCase):
    def test_provider_create_session_success(self):
        payment = Payment()
        provider = StripeProviderV3(secret_key=SECRET_KEY)
        return_value = {
            "id": "cs_test_a1IFfCFshMozn2NWE5a5g3P4NpJQOMuqxBbwpuWwCDXXcJm0MP2eaY0cLI",
            "url": "https://checkout.stripe.com/c/pay/cs_test_a1IFfCFshMozn2NWE5a5g3P4NpJQOMuqxBbwpuWwCDXXcJm0MP2eaY0cLI",
            "status": "open",
            "payment_status": "unpaid",
            "payment_intent": "pi_1IuobHAAvpvfo7rv9xqrPPE2",
        }
        with patch("json.dumps"):
            with patch("stripe.checkout.Session.create", return_value=return_value):
                with self.assertRaises(RedirectNeeded):
                    provider.get_form(payment)
                    self.assertTrue("url" in payment.attrs.session)
                    self.assertTrue("id" in payment.attrs.session)
        self.assertEqual(payment.status, PaymentStatus.WAITING)

    def test_provider_create_session_bad_key(self):
        payment = Payment()
        provider = StripeProviderV3(secret_key=SECRET_KEY_BAD)
        with patch("stripe.checkout.Session.create"):
            with self.assertRaises(PaymentError):
                provider.get_form(payment)
        self.assertEqual(payment.status, PaymentStatus.WAITING)
