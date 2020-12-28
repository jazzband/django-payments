from decimal import Decimal
import json

import stripe

from .forms import ModalPaymentForm, PaymentForm
from .. import RedirectNeeded, PaymentError, PaymentStatus
from ..core import BasicProvider


class StripeProvider(BasicProvider):
    """Provider backend using `Stripe <https://stripe.com/>`_.

    This backend does not support fraud detection.

    :param secret_key: Secret key assigned by Stripe.
    :param public_key: Public key assigned by Stripe.
    :param name: A friendly name for your store.
    :param image: Your logo.
    """

    form_class = ModalPaymentForm

    def __init__(self, public_key, secret_key, image='', name='', **kwargs):
        stripe.api_key = secret_key
        self.secret_key = secret_key
        self.public_key = public_key
        self.image = image
        self.name = name
        super().__init__(**kwargs)

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
        except stripe.InvalidRequestError:
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
    """Provider backend using `Stripe <https://stripe.com/>`_, form-based.

    This backend implements payments using `Stripe <https://stripe.com/>`_ but
    the credit card data is collected by your site.

    Parameters are the same as  :class:`~StripeProvider`.
    """
    form_class = PaymentForm
