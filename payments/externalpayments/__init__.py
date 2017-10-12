from __future__ import unicode_literals

from django.http import HttpResponseRedirect, HttpResponseForbidden, HttpResponse
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .forms import OrderIdForm, IBANBankingForm
from .. import PaymentError, PaymentStatus, RedirectNeeded
from ..core import BasicProvider

class DirectPaymentProvider(BasicProvider):
    '''
        Payment is done manually e.g. cash on delivery, voucher in restaurant.
        Payments are just a placeholder; to allow every further operation set to CONFIRMED.

        skipform:
            doesn't show form with data
        usetoken:
            if you don't verify the name; don't allow people
            supplying others order numbers (use token)
            because it is much longer it defaults to off
        prefix:
            reference: add prefix to payment id

    '''

    def __init__(self, skipform=True, confirm=False,
                 usetoken=False, prefix="", **kwargs):
        super(DirectPaymentProvider, self).__init__(**kwargs)
        self.skipform = skipform
        self.prefix = prefix
        self.usetoken = usetoken
        self.confirm = confirm
        if not self._capture:
            raise ImproperlyConfigured(
                'Direct Payments do not support pre-authorization.')

    def get_form(self, payment, data=None):
        if not payment.id:
            payment.save()
        if not payment.transaction_id:
            if self.usetoken:
                payment.transaction_id = "{}{}-{}".format(self.prefix, payment.id, payment.token)
            else:
                payment.transaction_id = "{}{}".format(self.prefix, payment.id)
            payment.save()
        if not self.skipform:
            if not data or not data.get("order", None):
                return OrderIdForm({"order": payment.transaction_id},
                                   payment=payment,
                                   provider=self,
                                   hidden_inputs=False)
        if self.confirm:
            payment.change_status(PaymentStatus.CONFIRMED)
        else:
            payment.change_status(PaymentStatus.WAITING)
        raise RedirectNeeded(payment.get_success_url())

    def refund(self, payment, amount=None):
        if not amount:
            amount = payment.total
        payment.change_status(PaymentStatus.REFUNDED)
        return amount

class BankTransferProvider(BasicProvider):
    '''
        Banking software or human confirms transaction.
        Because there is no security problems if somebody pays for somebody else and references can not hold many characters, only the id is required.
        The form is used to show the user the data he has to send.
        iban:
            IBAN number
        bic:
            BIC number
        prefix:
            reference: add prefix to payment id
        confirm:
            set PaymentStatus to CONFIRMED after user confirms
    '''

    def __init__(self, iban, bic, confirm=False,
                 prefix="", **kwargs):
        if len(iban) <= 10 or len(bic) <= 4:
            raise ImproperlyConfigured("Wrong IBAN or BIC")
        self.iban = iban.upper()
        self.bic = bic.upper()
        self.confirm = confirm
        self.prefix = prefix
        super(BankTransferProvider, self).__init__(**kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                'Advance Payment does not support pre-authorization.')

    def get_hidden_fields(self, payment):
        return {
            'iban': self.iban,
            'bic': self.bic,
            'order': payment.transaction_id
        }

    def get_form(self, payment, data=None):
        if not payment.id:
            payment.save()
        if not payment.transaction_id:
            payment.transaction_id = "{}{}".format(self.prefix, payment.id)
            payment.save()
        if not data or not data.get("order", None):
            return IBANBankingForm(self.get_hidden_fields(payment), payment=payment, provider=self, hidden_inputs=False)
        if self.confirm:
            payment.change_status(PaymentStatus.CONFIRMED)
        else:
            payment.change_status(PaymentStatus.WAITING)
        raise RedirectNeeded(payment.get_success_url())

    def refund(self, payment, amount=None):
        if not amount:
            amount = payment.total
        payment.change_status(PaymentStatus.REFUNDED)
        return amount
