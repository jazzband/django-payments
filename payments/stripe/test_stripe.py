from __future__ import unicode_literals
from mock import patch, MagicMock
from unittest import TestCase
import stripe

from payments.stripe import StripeProvider

from payments import RedirectNeeded


SECRET_KEY = '1234abcd'
PUBLIC_KEY = 'abcd1234'


class Payment(MagicMock):

    id = 1
    description = 'payment'
    currency = 'USD'
    delivery = 10
    status = 'waiting'
    tax = 10
    total = 100
    captured_amount = 0
    transaction_id = None

    def change_status(self, status):
        self.status = status

    def get_failure_url(self):
        return 'http://cancel.com'

    def get_process_url(self):
        return 'http://example.com'

    def get_purchased_items(self):
        return []

    def get_success_url(self):
        return 'http://success.com'


class TestStripeProvider(TestCase):

    def test_form_contains_stripe_script(self):
        payment = Payment()
        store_name = 'Test store'
        provider = StripeProvider(
            name=store_name,
            secret_key=SECRET_KEY, public_key=PUBLIC_KEY)
        form = provider.get_form(payment)
        self.assertTrue(
            '<script class="stripe-button" data-amount="10000" '
            'data-currency="USD" data-description="payment" data-image="" '
            'data-key="%s" data-name="%s" '
            'src="https://checkout.stripe.com/checkout.js"></script>' % (
                PUBLIC_KEY, store_name)
            in str(form))

    def test_provider_raises_redirect_needed_when_token_does_not_exist(self):
        payment = Payment()
        provider = StripeProvider(
            name='Example.com store',
            secret_key=SECRET_KEY, public_key=PUBLIC_KEY)
        data = {}
        with self.assertRaises(RedirectNeeded) as exc:
            provider.get_form(payment, data)
            self.assertEqual(exc.args[0], payment.get_failure_url())
        self.assertEqual(payment.status, 'rejected')

    def test_provider_raises_redirect_needed_on_success(self):
        payment = Payment()
        provider = StripeProvider(
            name='Example.com store',
            secret_key=SECRET_KEY, public_key=PUBLIC_KEY)
        data = {'stripeToken': 'abcd'}
        with patch('stripe.Charge.create'):
            with self.assertRaises(RedirectNeeded) as exc:
                provider.get_form(payment, data)
                self.assertEqual(exc.args[0], payment.get_success_url())
        self.assertEqual(payment.status, 'confirmed')
        self.assertEqual(payment.captured_amount, payment.total)

    def test_provider_shows_validation_error_message(self):
        error_msg = 'Error message'
        payment = Payment()
        provider = StripeProvider(
            name='Example.com store',
            secret_key=SECRET_KEY, public_key=PUBLIC_KEY)
        data = {'stripeToken': 'abcd'}
        with patch('stripe.Charge.create') as mocked_charge:
            mocked_charge.side_effect = stripe.CardError(
                error_msg, param=None, code=None)
            form = provider.get_form(payment, data=data)
            self.assertEqual(form.errors['__all__'][0], error_msg)
        self.assertEqual(payment.status, 'error')
        self.assertEqual(payment.captured_amount, 0)
