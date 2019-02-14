from __future__ import unicode_literals
from decimal import Decimal
import json

import stripe

from .forms import ModalPaymentForm, PaymentForm
from .. import RedirectNeeded, PaymentError, PaymentStatus
from ..core import BasicProvider


class StripeProvider(BasicProvider):

    form_class = ModalPaymentForm

    def __init__(self, public_key, secret_key, image='', name='', **kwargs):
        stripe.api_key = secret_key
        self.secret_key = secret_key
        self.public_key = public_key
        self.image = image
        self.name = name
        super(StripeProvider, self).__init__(**kwargs)

    def get_form(self, payment, data=None):
        if payment.status == PaymentStatus.WAITING:
            payment.change_status(PaymentStatus.INPUT)
        form = self.form_class(
            data=data, payment=payment, provider=self)

        if form.is_valid():
            form.save()
            raise RedirectNeeded(payment.get_success_url())
        return form

    def capture(self, payment, amount=None):
        amount = int((amount or payment.total) * 100)
        charge = stripe.Charge.retrieve(payment.transaction_id)
        try:
            charge.capture(amount=amount)
        except stripe.InvalidRequestError as e:
            payment.change_status(PaymentStatus.REFUNDED)
            raise PaymentError('Payment already refunded')
        payment.attrs.capture = json.dumps(charge)
        return Decimal(amount) / 100

    def release(self, payment):
        charge = stripe.Charge.retrieve(payment.transaction_id)
        charge.refund()
        payment.attrs.release = json.dumps(charge)

    def refund(self, payment, amount=None):
        amount = int((amount or payment.total) * 100)
        charge = stripe.Charge.retrieve(payment.transaction_id)
        charge.refund(amount=amount)
        payment.attrs.refund = json.dumps(charge)
        return Decimal(amount) / 100


class StripeCardProvider(StripeProvider):
    form_class = PaymentForm
