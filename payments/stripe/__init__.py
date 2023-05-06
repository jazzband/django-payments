import json
import warnings
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal
from typing import Optional

import stripe

from .. import PaymentError
from .. import PaymentStatus
from .. import RedirectNeeded
from ..core import BasicProvider
from .forms import ModalPaymentForm
from .forms import PaymentForm
from .forms import PaymentFormV3


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
            "This provider uses the deprecated v2 API, please use `payments.stripe.StripeProviderV3`",
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
        except stripe.InvalidRequestError:
            payment.change_status(PaymentStatus.REFUNDED)
            raise PaymentError("Payment already refunded")
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


@dataclass
class StripeProductData:
    name: str
    description: Optional[str] = field(init=False, repr=False, default=None)
    images: Optional[str] = field(init=False, repr=False, default=None)
    metadata: Optional[dict] = field(init=False, repr=False, default=None)
    tax_code: Optional[str] = field(init=False, repr=False, default=None)


@dataclass
class StripePriceData:
    currency: str
    product_data: StripeProductData
    unit_amount: int
    recurring: Optional[dict] = field(init=False, repr=False, default=None)
    tax_behavior: Optional[str] = field(init=False, repr=False, default=None)


@dataclass
class StripeLineItem:
    price_data: StripePriceData
    quantity: int
    adjustable_quantity: Optional[dict] = field(init=False, repr=False, default=None)
    dynamic_tax_rates: Optional[dict] = field(init=False, repr=False, default=None)
    tax_rates: Optional[str] = field(init=False, repr=False, default=None)


class StripeProviderV3(BasicProvider):
    """Provider backend using `Stripe <https://stripe.com/>` api version 3_.

    This backend does not support fraud detection.

    :param api_key: Secret key assigned by Stripe.
    :param use_token: Use instance.token instead of instance.pk in client_reference_id
    """

    form_class = PaymentFormV3

    def __init__(
        self,
        api_key,
        use_token=True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.use_token = use_token

    def get_form(self, payment, data=None):
        if not payment.transaction_id:
            try:
                session = self.create_session(payment)
            except PaymentError as pe:
                payment.change_status(PaymentStatus.ERROR, str(pe))
                raise PaymentError(pe)
            else:
                payment.attrs.session = session
                payment.transaction_id = session.get("id", None)
                payment.save()

        if "url" not in payment.attrs.session:
            raise PaymentError("Stripe returned a session without a URL")

        raise RedirectNeeded(payment.attrs.session.get("url"))

    def create_session(self, payment):
        """Makes the call to Stripe to create the Checkout Session"""
        if not payment.transaction_id:
            stripe.api_key = self.api_key
            session_data = {
                "line_items": self.get_line_items(payment),
                "mode": "payment",
                "success_url": payment.get_success_url(),
                "cancel_url": payment.get_failure_url(),
                "client_reference_id": payment.token if self.use_token else payment.pk,
            }
            # Patch session with billing email if exists
            if payment.billing_email:
                session_data.update({"customer_email": payment.billing_email})
            try:
                return stripe.checkout.Session.create(**session_data)
            except stripe.error.StripeError as e:
                # Payment has been declined
                raise PaymentError(e)
        else:
            raise PaymentError("This payment has already been processed.")

    def refund(self, payment, amount=None):
        if payment.status == PaymentStatus.CONFIRMED:
            amount = int((amount or payment.total) * 100)
            payment_intent = payment.attrs.session.get("payment_intent", None)
            if not payment_intent:
                raise PaymentError("Can't Refund, payment_intent does not exist")
            stripe.api_key = self.api_key
            try:
                refund = stripe.Refund.create(
                    payment_intent=payment_intent,
                    amount=amount,
                    reason="requested_by_customer",
                )
            except stripe.StripeError as e:
                raise PaymentError(e)
            else:
                payment.attrs.refund = json.dumps(refund)
                payment.save()
                payment.change_status(PaymentStatus.REFUNDED)
                return Decimal(amount) / 100

        raise PaymentError("Only Confirmed payments can be refunded")

    def status(self, payment):
        if payment.status == PaymentStatus.WAITING:
            stripe.api_key = self.api_key
            session = stripe.checkout.Session.retrieve(payment.transaction_id)
            if session.payment_status == "paid":
                payment.change_status(PaymentStatus.CONFIRMED)

        return payment

    def get_line_items(self, payment):
        order_no = payment.token if self.use_token else payment.pk
        product_data = StripeProductData(name="Order #{}".format(order_no))

        price_data = StripePriceData(
            currency=payment.currency,
            unit_amount=int(payment.total * 100),
            product_data=product_data,
        )
        line_item = StripeLineItem(
            quantity=1,
            price_data=price_data,
        )
        return [asdict(line_item)]
