from __future__ import unicode_literals
from decimal import Decimal
from unittest import TestCase
from mock import patch, NonCallableMock

from payments import core
from .forms import CreditCardPaymentFormWithName, PaymentForm
from .models import BasePayment
from . import PaymentStatus


class TestHelpers(TestCase):
    @patch('payments.core.PAYMENT_HOST', new_callable=NonCallableMock)
    def test_text_get_base_url(self, host):
        host.__str__ = lambda x: "example.com/string"
        self.assertEqual(core.get_base_url(), "https://example.com/string")

    @patch('payments.core.PAYMENT_HOST')
    def test_callable_get_base_url(self, host):
        host.return_value = "example.com/callable"
        self.assertEqual(core.get_base_url(), "https://example.com/callable")


class TestProviderFactory(TestCase):

    def test_provider_factory(self):
        core.provider_factory('default')

    def test_provider_does_not_exist(self):
        self.assertRaises(ValueError, core.provider_factory, 'fake_provider')


class TestBasePayment(TestCase):

    def test_payment_attributes(self):
        payment = BasePayment(
            extra_data='{"attr1": "test1", "attr2": "test2"}')
        self.assertEqual(payment.attrs.attr1, "test1")
        self.assertEqual(payment.attrs.attr2, 'test2')

    def test_capture_with_wrong_status(self):
        payment = BasePayment(variant='default', status=PaymentStatus.WAITING)
        self.assertRaises(ValueError, payment.capture)

    @patch('payments.dummy.DummyProvider.capture')
    def test_capture_preauth_successfully(self, mocked_capture_method):
        amount = Decimal('20')
        with patch.object(BasePayment, 'save') as mocked_save_method:
            mocked_save_method.return_value = None
            mocked_capture_method.return_value = amount

            payment = BasePayment(variant='default', status=PaymentStatus.PREAUTH)
            payment.capture(amount)

            self.assertEqual(payment.status, PaymentStatus.CONFIRMED)
            self.assertEqual(payment.captured_amount, amount)
        self.assertEqual(mocked_capture_method.call_count, 1)

    @patch('payments.dummy.DummyProvider.capture')
    def test_capture_preauth_without_amount(self, mocked_capture_method):
        amount = None
        with patch.object(BasePayment, 'save') as mocked_save_method:
            mocked_save_method.return_value = None
            mocked_capture_method.return_value = amount

            captured_amount = Decimal('100')
            status = PaymentStatus.PREAUTH
            payment = BasePayment(variant='default', status=status,
                                  captured_amount=captured_amount)
            payment.capture(amount)

            self.assertEqual(payment.status, status)
            self.assertEqual(payment.captured_amount, captured_amount)
        self.assertEqual(mocked_capture_method.call_count, 1)

    def test_release_with_wrong_status(self):
        payment = BasePayment(variant='default', status=PaymentStatus.WAITING)
        self.assertRaises(ValueError, payment.release)

    @patch('payments.dummy.DummyProvider.release')
    def test_release_preauth_successfully(self, mocked_release_method):
        with patch.object(BasePayment, 'save') as mocked_save_method:
            mocked_save_method.return_value = None

            payment = BasePayment(variant='default', status=PaymentStatus.PREAUTH)
            payment.release()
            self.assertEqual(payment.status, PaymentStatus.REFUNDED)
        self.assertEqual(mocked_release_method.call_count, 1)

    def test_refund_with_wrong_status(self):
        payment = BasePayment(variant='default', status=PaymentStatus.WAITING)
        self.assertRaises(ValueError, payment.refund)

    def test_refund_too_high_amount(self):
        payment = BasePayment(variant='default', status=PaymentStatus.CONFIRMED,
                              captured_amount=Decimal('100'))
        self.assertRaises(ValueError, payment.refund, Decimal('200'))

    @patch('payments.dummy.DummyProvider.refund')
    def test_refund_without_amount(self, mocked_refund_method):
        refund_amount = None
        with patch.object(BasePayment, 'save') as mocked_save_method:
            mocked_save_method.return_value = None
            mocked_refund_method.return_value = refund_amount

            captured_amount = Decimal('200')
            status = PaymentStatus.CONFIRMED
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
        status = PaymentStatus.CONFIRMED
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

            payment = BasePayment(variant='default', status=PaymentStatus.CONFIRMED,
                                  captured_amount=captured_amount)
            payment.refund(refund_amount)
            self.assertEqual(payment.status, PaymentStatus.REFUNDED)
            self.assertEqual(payment.captured_amount, Decimal('0'))
        self.assertEqual(mocked_refund_method.call_count, 1)


class TestCreditCardPaymentForm(TestCase):

    def setUp(self):
        self.data = {
            'name': 'John Doe',
            'number': '4716124728800975',
            'expiration_0': '5',
            'expiration_1': '2020',
            'cvv2': '123'}

    def test_form_verifies_card_number(self):
        form = CreditCardPaymentFormWithName(data=self.data)
        self.assertTrue(form.is_valid())

    def test_form_raises_error_for_invalid_card_number(self):
        data = dict(self.data)
        data.update({'number': '1112223334445556'})
        form = CreditCardPaymentFormWithName(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('number', form.errors)

    def test_form_raises_error_for_invalid_cvv2(self):
        data = dict(self.data)
        data.update({'cvv2': '12345'})
        form = CreditCardPaymentFormWithName(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('cvv2', form.errors)


class TestPaymentForm(TestCase):

    def test_form_contains_hidden_fields(self):
        data = {
            'field1': 'value1',
            'field2': 'value2',
            'field3': 'value3',
            'field4': 'value4'}

        form = PaymentForm(data=data, hidden_inputs=True)
        self.assertEqual(len(form.fields), len(data))
        self.assertEqual(form.fields['field1'].initial, 'value1')

class TestCardIssuer(TestCase):
    def test_mastercard(self):
        self.assertEqual(core.get_credit_card_issuer("2720999018275485"), ('mastercard', 'MasterCard'))
        self.assertEqual(core.get_credit_card_issuer("5101395940513451"), ('mastercard', 'MasterCard'))
        self.assertEqual(core.get_credit_card_issuer("5469166706524768"), ('mastercard', 'MasterCard'))

    def test_visa(self):
        self.assertEqual(core.get_credit_card_issuer("4929299255922609"), ('visa', 'VISA'))
        self.assertEqual(core.get_credit_card_issuer("4539883983691685"), ('visa', 'VISA'))
        self.assertEqual(core.get_credit_card_issuer("4916396455393611281"), ('visa', 'VISA'),"19 digit Visa Card")

    def test_discover(self):
        self.assertEqual(core.get_credit_card_issuer("6011281400356614"), ('discover', 'Discover'))
        self.assertEqual(core.get_credit_card_issuer("6011223438090674"), ('discover', 'Discover'))
        self.assertEqual(core.get_credit_card_issuer("6011509478386387430"), ('discover', 'Discover'),"19 digit Discover Card")

    def test_amex(self):
        self.assertEqual(core.get_credit_card_issuer("341841172626538"), ('amex', 'American Express'))
        self.assertEqual(core.get_credit_card_issuer("348710065929999"), ('amex', 'American Express'))
        self.assertEqual(core.get_credit_card_issuer("341473920579841"), ('amex', 'American Express'))

    
