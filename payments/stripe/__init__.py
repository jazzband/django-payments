from __future__ import annotations

import json
import warnings
from decimal import Decimal

import stripe

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded
from payments.core import BasicProvider

from .forms import ModalPaymentForm
from .forms import PaymentForm
from .providers import StripeProviderV3


class StripeProvider(BasicProvider):
    """Provider backend using `Stripe <https://stripe.com/>`_.

    This backend does not support fraud detection.

    :param secret_key: Secret key assigned by Stripe.
    :param public_key: Public key assigned by Stripe.
    :param name: A friendly name for your store.
    :param image: Your logo.
    """

    form_class = ModalPaymentForm

    def __init__(self, public_key, secret_key, image="", name="", **kwargs):
        stripe.api_key = secret_key
        self.secret_key = secret_key
        self.public_key = public_key
        self.image = image
        self.name = name
        super().__init__(**kwargs)
        warnings.warn(
            "This provider uses the deprecated v2 API, please use `payments.stripe.StripeProviderV3`",  # noqa: E501
            DeprecationWarning,
            stacklevel=2,
        )

    def get_form(self, payment, data=None):
        if payment.status == PaymentStatus.WAITING:
            payment.change_status(PaymentStatus.INPUT)
        form = self.form_class(data=data, payment=payment, provider=self)

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
            raise PaymentError("Payment already refunded") from e
        payment.extra_data["capture"] = json.dumps(charge)
        return Decimal(amount) / 100

    def release(self, payment):
        charge = stripe.Charge.retrieve(payment.transaction_id)
        charge.refund()
        payment.extra_data["release"] = json.dumps(charge)

    def refund(self, payment, amount=None):
        amount = int((amount or payment.total) * 100)
        charge = stripe.Charge.retrieve(payment.transaction_id)
        charge.refund(amount=amount)
        payment.extra_data["refund"] = json.dumps(charge)
        return Decimal(amount) / 100


class StripeCardProvider(StripeProvider):
    """Provider backend using `Stripe <https://stripe.com/>`_, form-based.

    This backend implements payments using `Stripe <https://stripe.com/>`_ but
    the credit card data is collected by your site.

    Parameters are the same as  :class:`~StripeProvider`.
    """

    form_class = PaymentForm


__all__ = ["StripeProviderV3"]
