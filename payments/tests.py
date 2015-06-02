from __future__ import unicode_literals
from decimal import Decimal
from unittest import TestCase
from mock import patch, Mock

import django

if hasattr(django, 'setup'):
    django.setup()

from . import provider_factory
from .models import BasePayment
from .dotpay.tests import TestDotpayProvider
from .paypal.tests import TestPaypalProvider
from .stripe.tests import TestStripeProvider
from .wallet.tests import TestGoogleWalletProvider
from .dummy.tests import TestDummy3DSProvider


__all__ = ['TestDotpayProvider', 'TestGoogleWalletProvider',
           'TestPaypalProvider', 'TestStripeProvider', 'TestDummy3DSProvider']


class TestProviderFactory(TestCase):

    def test_provider_factory(self):
        provider_factory('default')

    def test_provider_does_not_exist(self):
        self.assertRaises(ValueError, provider_factory, 'fake_provider')


class TestBasePayment(TestCase):

    def test_payment_attributes(self):
        payment = BasePayment(
            extra_data='{"attr1": "test1", "attr2": "test2"}')
        self.assertEqual(payment.attrs.attr1, "test1")
        self.assertEqual(payment.attrs.attr2, 'test2')

    def test_capture_with_wrong_status(self):
        payment = BasePayment(variant='default', status='waiting')
        self.assertRaises(ValueError, payment.capture)

    @patch('payments.dummy.DummyProvider.capture')
    def test_capture_preauth_successfully(self, mocked_capture_method):
        amount = Decimal('20')
        with patch.object(BasePayment, 'save') as mocked_save_method:
            mocked_save_method.return_value = None
            mocked_capture_method.return_value = amount

            payment = BasePayment(variant='default', status='preauth')
            payment.capture(amount)

            self.assertEqual(payment.status, 'confirmed')
            self.assertEqual(payment.captured_amount, amount)
        self.assertEqual(mocked_capture_method.call_count, 1)

    @patch('payments.dummy.DummyProvider.capture')
    def test_capture_preauth_without_amount(self, mocked_capture_method):
        amount = None
        with patch.object(BasePayment, 'save') as mocked_save_method:
            mocked_save_method.return_value = None
            mocked_capture_method.return_value = amount

            captured_amount = Decimal('100')
            status = 'preauth'
            payment = BasePayment(variant='default', status=status,
                                  captured_amount=captured_amount)
            payment.capture(amount)

            self.assertEqual(payment.status, status)
            self.assertEqual(payment.captured_amount, captured_amount)
        self.assertEqual(mocked_capture_method.call_count, 1)

    def test_release_with_wrong_status(self):
        payment = BasePayment(variant='default', status='waiting')
        self.assertRaises(ValueError, payment.release)

    @patch('payments.dummy.DummyProvider.release')
    def test_release_preauth_successfully(self, mocked_release_method):
        with patch.object(BasePayment, 'save') as mocked_save_method:
            mocked_save_method.return_value = None

            payment = BasePayment(variant='default', status='preauth')
            payment.release()
            self.assertEqual(payment.status, 'refunded')
        self.assertEqual(mocked_release_method.call_count, 1)

    def test_refund_with_wrong_status(self):
        payment = BasePayment(variant='default', status='waiting')
        self.assertRaises(ValueError, payment.refund)

    def test_refund_too_high_amount(self):
        payment = BasePayment(variant='default', status='confirmed',
                              captured_amount=Decimal('100'))
        self.assertRaises(ValueError, payment.refund, Decimal('200'))

    @patch('payments.dummy.DummyProvider.refund')
    def test_refund_without_amount(self, mocked_refund_method):
        refund_amount = None
        with patch.object(BasePayment, 'save') as mocked_save_method:
            mocked_save_method.return_value = None
            mocked_refund_method.return_value = refund_amount

            captured_amount = Decimal('200')
            status = 'confirmed'
            payment = BasePayment(variant='default', status=status,
                                  captured_amount=captured_amount)
            payment.refund(refund_amount)
            self.assertEqual(payment.status, status)
            self.assertEqual(payment.captured_amount, captured_amount)
        self.assertEqual(mocked_refund_method.call_count, 0)

    @patch('payments.dummy.DummyProvider.refund')
    def test_refund_partial_success(self, mocked_refund_method):
        refund_amount = Decimal('100')
        captured_amount = Decimal('200')
        status = 'confirmed'
        with patch.object(BasePayment, 'save') as mocked_save_method:
            mocked_save_method.return_value = None
            mocked_refund_method.return_value = refund_amount

            payment = BasePayment(variant='default', status=status,
                                  captured_amount=captured_amount)
            payment.refund(refund_amount)
            self.assertEqual(payment.status, status)
            self.assertEqual(payment.captured_amount, Decimal('100'))
        self.assertEqual(mocked_refund_method.call_count, 1)

    @patch('payments.dummy.DummyProvider.refund')
    def test_refund_fully_success(self, mocked_refund_method):
        refund_amount = Decimal('200')
        captured_amount = Decimal('200')
        with patch.object(BasePayment, 'save') as mocked_save_method:
            mocked_save_method.return_value = None
            mocked_refund_method.return_value = refund_amount

            payment = BasePayment(variant='default', status='confirmed',
                                  captured_amount=captured_amount)
            payment.refund(refund_amount)
            self.assertEqual(payment.status, 'refunded')
            self.assertEqual(payment.captured_amount, Decimal('0'))
        self.assertEqual(mocked_refund_method.call_count, 1)
