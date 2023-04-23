import json
from decimal import Decimal
from dataclasses import dataclass, field, asdict
from typing import Optional


try:
    import stripe
except ImportError as exc:
    raise ImportError(
        "You need to install `stripe>=2.6.0` onto your environment"
    ) from exc

from .. import PaymentError
from .. import PaymentStatus
from .. import RedirectNeeded
from ..core import BasicProvider
from .forms import ModalPaymentForm
from .forms import PaymentForm


@dataclass
class StripeProductData:
    name: str
    description: Optional[str] = field(init=False, repr=False, default=None)
    images: Optional[list[str]] = field(init=False, repr=False, default=None)
    metadata: Optional[dict] = field(init=False, repr=False, default=None)
    tax_code: Optional[str] = field(init=False, repr=False, default=None)


@dataclass
class StripePriceData:
    currency: str
    product_data: StripeProductData
    unit_amount_decimal: Decimal
    recurring: Optional[dict] = field(init=False, repr=False, default=None)
    tax_behavior: Optional[str] = field(init=False, repr=False, default=None)


@dataclass
class StripeLineItem:
    price_data: StripePriceData
    quantity: int
    adjustable_quantity: Optional[dict] = field(init=False, repr=False, default=None)
    dynamic_tax_rates: Optional[dict] = field(init=False, repr=False, default=None)
    tax_rates: Optional[str] = field(init=False, repr=False, default=None)


class StripeProvider(BasicProvider):
    """Provider backend using `Stripe <https://stripe.com/>`_.

    This backend does not support fraud detection.

    :param secret_key: Secret key assigned by Stripe.
    :param public_key: Public key assigned by Stripe.
    :param name: A friendly name for your store.
    :param image: Your logo.
    :param show_form: Shows the Pay Now button, default True
    :param payment_method_types: From Stripe API, default ["card"]
    """

    form_class = PaymentForm

    def __init__(
        self,
        public_key,
        secret_key,
        image="",
        name="",
        show_form=True,
        payment_method_types=["card"],
        **kwargs,
    ):
        self.secret_key = secret_key
        self.public_key = public_key
        self.image = image
        self.name = name
        self.show_form = show_form
        self.payment_method_types = payment_method_types
        super().__init__(**kwargs)

    def get_form(self, payment, data=None):
        if payment.status == PaymentStatus.WAITING:
            payment.change_status(PaymentStatus.INPUT)
        form = self.form_class(data=data, payment=payment, provider=self)

        if form.is_valid():
            form.save()
            raise RedirectNeeded(payment.get_success_url())
        return form

    def capture(self, payment, amount=None):
        # API v3 does not support Capture
        pass

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

    def get_line_items(self, payment):
        product_data = StripeProductData(name="Order #{}".format(payment.pk))
        price_data = StripePriceData(
            currency=payment.currency,
            unit_amount_decimal=payment.total,
            product_data=product_data,
        )
        line_item = StripeLineItem(
            quantity=1,
            price_data=price_data,
        )
        return [asdict(line_item)]


class StripeCardProvider(StripeProvider):
    """Provider backend using `Stripe <https://stripe.com/>`_, form-based.

    This backend implements payments using `Stripe <https://stripe.com/>`_ but
    the credit card data is collected by your site.

    Parameters are the same as  :class:`~StripeProvider`.
    """

    form_class = PaymentForm
