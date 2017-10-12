from unittest import TestCase
try:
    from unittest.mock import MagicMock
except ImportError:
    from mock import MagicMock
from . import DirectPaymentProvider, BankTransferProvider
from .. import PaymentStatus, RedirectNeeded
from ..testcommon import create_test_payment

Payment = create_test_payment()


class TestDirectProvider(TestCase):
    def setUp(self):
        self.payment = Payment()

    def test_confirm_skip(self):
        provider = DirectPaymentProvider(confirm=True)
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        with self.assertRaises(RedirectNeeded):
            provider.get_form(self.payment)
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)

    def test_confirm_noskip(self):
        provider = DirectPaymentProvider(skipform=False, confirm=True)
        form = provider.get_form(self.payment)
        form.is_valid()
        form.clean()
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        with self.assertRaises(RedirectNeeded):
            provider.get_form(self.payment, form.cleaned_data)
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)

    def test_noconfirm_skip(self):
        provider = DirectPaymentProvider()
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        with self.assertRaises(RedirectNeeded):
            provider.get_form(self.payment)
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)

    def test_noconfirm_noskip(self):
        provider = DirectPaymentProvider(skipform=False)
        form = provider.get_form(self.payment)
        form.is_valid()
        form.clean()
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        with self.assertRaises(RedirectNeeded):
            provider.get_form(self.payment, form.cleaned_data)
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)

class TestBankTransferProvider(TestCase):
    def setUp(self):
        self.payment = Payment()

    def test_bank_transfer_confirms(self):
        provider = BankTransferProvider(iban="GL5604449876543210", bic="DABAIE2D", confirm=True)
        form = provider.get_form(self.payment)
        form.is_valid()
        form.clean()
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        with self.assertRaises(RedirectNeeded):
            provider.get_form(self.payment, form.cleaned_data)
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)

    def test_bank_transfer_confirms_not(self):
        provider = BankTransferProvider("GL5604449876543210", "DABAIE2D", confirm=False)
        form = provider.get_form(self.payment)
        form.is_valid()
        form.clean()
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        with self.assertRaises(RedirectNeeded):
            provider.get_form(self.payment, form.cleaned_data)
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
