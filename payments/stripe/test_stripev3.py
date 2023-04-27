from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch

import stripe

from .. import PaymentStatus
from .. import RedirectNeeded
from . import StripeProviderV3

# Secret key from https://stripe.com/docs/api/authentication
SECRET_KEY = "sk_test_4eC39HqLyjWDarjtT1zdp7dc"


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
    # def test_provider_raises_redirect_needed_when_token_does_not_exist(self):
    #     payment = Payment()
    #     provider = StripeProviderV3(name="Example.com store", secret_key=SECRET_KEY)
    #     data = {}
    #     with self.assertRaises(RedirectNeeded) as exc:
    #         provider.get_form(payment, data)
    #         self.assertEqual(exc.args[0], payment.get_failure_url())
    #     self.assertEqual(payment.status, PaymentStatus.REJECTED)

    # def test_provider_raises_redirect_needed_on_success(self):
    #     payment = Payment()
    #     provider = StripeProviderV3(name="Example.com store", secret_key=SECRET_KEY)
    #     data = {"stripeToken": "abcd"}
    #     with patch("json.dumps"):
    #         with patch("stripe.Charge.create"):
    #             with self.assertRaises(RedirectNeeded) as exc:
    #                 provider.get_form(payment, data)
    #                 self.assertEqual(exc.args[0], payment.get_success_url())
    #     self.assertEqual(payment.status, PaymentStatus.CONFIRMED)
    #     self.assertEqual(payment.captured_amount, payment.total)

    # def test_provider_shows_validation_error_message(self):
    #     error_msg = "Error message"

    #     payment = Payment()
    #     provider = StripeProviderV3(name="Example.com store", secret_key=SECRET_KEY)
    #     data = {"stripeToken": "abcd"}
    #     with mock_stripe_Session_create(error_msg=error_msg):
    #         with mock_stripe_Charge_retrieve():
    #             form = provider.get_form(payment, data=data)
    #             self.assertEqual(form.errors["__all__"][0], error_msg)
    #     self.assertEqual(payment.status, PaymentStatus.ERROR)
    #     self.assertEqual(payment.message, error_msg)
    #     self.assertEqual(payment.captured_amount, 0)

    def test_provider_detect_already_processed_payment(self):
        payment = Payment()
        payment.transaction_id = "existing_transaction_id"
        provider = StripeProviderV3(name="Example.com store", secret_key=SECRET_KEY)
        data = {"stripeToken": "abcd"}
        with mock_stripe_Session_create():
            form = provider.get_form(payment, data=data)
            msg = "This payment has already been processed."
            self.assertEqual(form.errors["__all__"][0], msg)
