from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any

import stripe
from django.http import JsonResponse

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded
from payments.core import BasicProvider
from payments.forms import PaymentForm as BasePaymentForm


@dataclass
class StripeProductData:
    name: str
    description: str | None = field(init=False, repr=False, default=None)
    images: str | None = field(init=False, repr=False, default=None)
    metadata: dict | None = field(init=False, repr=False, default=None)
    tax_code: str | None = field(init=False, repr=False, default=None)


@dataclass
class StripePriceData:
    currency: str
    product_data: StripeProductData
    unit_amount: int
    recurring: dict | None = field(init=False, repr=False, default=None)
    tax_behavior: str | None = field(init=False, repr=False, default=None)


@dataclass
class StripeLineItem:
    price_data: StripePriceData
    quantity: int
    adjustable_quantity: dict | None = field(init=False, repr=False, default=None)
    dynamic_tax_rates: dict | None = field(init=False, repr=False, default=None)
    tax_rates: str | None = field(init=False, repr=False, default=None)


zero_decimal_currency: list = [
    "bif",
    "clp",
    "djf",
    "gnf",
    "jpy",
    "kmf",
    "krw",
    "mga",
    "pyg",
    "rwf",
    "ugx",
    "vnd",
    "vuv",
    "xaf",
    "xof",
    "xpf",
]
stripe_enabled_events: list = [
    "checkout.session.expired",
    "checkout.session.async_payment_failed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.completed",
]


class StripeProviderV3(BasicProvider):
    """Provider backend using `Stripe <https://stripe.com/>`_ api version 3.

    :param api_key: Secret key assigned by Stripe.
    :param use_token: Use instance.token instead of instance.pk in client_reference_id
    :param endpoint_secret: Endpoint Signing Secret.
    :param secure_endpoint: Validate the recieved data, useful for development.
    """

    form_class = BasePaymentForm

    def __init__(
        self,
        api_key,
        use_token=True,
        endpoint_secret=None,
        secure_endpoint=True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.use_token = use_token
        self.endpoint_secret = endpoint_secret
        self.secure_endpoint = secure_endpoint

    def get_form(self, payment, data=None):
        if not payment.transaction_id:
            try:
                session = self.create_session(payment)
            except PaymentError as pe:
                payment.change_status(PaymentStatus.ERROR, str(pe))
                raise pe
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

            # Patch session with billing name
            if payment.billing_first_name or payment.billing_last_name:
                session_data.update(
                    {
                        "metadata": {
                            "customer_name": f"{payment.billing_first_name} "
                            f"{payment.billing_last_name}"
                        }
                    }
                )
            try:
                return stripe.checkout.Session.create(**session_data)
            except stripe.error.StripeError as e:
                # Payment has been declined by Stripe, check Stripe Dashboard
                raise PaymentError(e) from e
        else:
            raise PaymentError("This payment has already been processed.")

    def refund(self, payment, amount=None) -> int:
        if payment.status == PaymentStatus.CONFIRMED:
            to_refund = amount or payment.total
            try:
                payment_intent = payment.attrs.session["payment_intent"]
            except Exception as e:
                raise PaymentError("Can't Refund, payment_intent does not exist") from e

            stripe.api_key = self.api_key
            try:
                refund = stripe.Refund.create(
                    payment_intent=payment_intent,
                    amount=self.convert_amount(payment.currency, to_refund),
                    reason="requested_by_customer",
                )
            except stripe.error.StripeError as e:
                raise PaymentError(e) from e
            else:
                payment.attrs.refund = json.dumps(refund)
                payment.save()
                payment.change_status(PaymentStatus.REFUNDED)
                return self.convert_amount(payment.currency, to_refund)

        raise PaymentError("Only Confirmed payments can be refunded")

    def status(self, payment):
        if payment.status == PaymentStatus.WAITING:
            stripe.api_key = self.api_key
            session = stripe.checkout.Session.retrieve(payment.transaction_id)
            if session.payment_status == "paid":
                payment.change_status(PaymentStatus.CONFIRMED)
                payment.attrs.session = session
                payment.save()

        return payment

    def get_line_items(self, payment) -> list:
        order_no = payment.token if self.use_token else payment.pk
        product_data = StripeProductData(name=f"Order #{order_no}")

        price_data = StripePriceData(
            currency=payment.currency.lower(),
            unit_amount=self.convert_amount(payment.currency, payment.total),
            product_data=product_data,
        )
        line_item = StripeLineItem(
            quantity=1,
            price_data=price_data,
        )
        # https://stacktuts.com/how-to-ignore-none-values-using-asdict-in-dataclasses
        return [asdict(line_item)]

    def convert_amount(self, currency, amount) -> int:
        # Check if the currency has to be converted to cents
        factor = 100 if currency.lower() not in zero_decimal_currency else 1

        return int(amount * factor)

    def return_event_payload(self, request) -> Any:
        if self.secure_endpoint:
            if "STRIPE_SIGNATURE" not in request.headers:
                raise PaymentError(
                    code=400, message="STRIPE_SIGNATURE not in request.headers"
                )

            try:
                return stripe.Webhook.construct_event(
                    request.body,
                    request.headers["STRIPE_SIGNATURE"],
                    self.endpoint_secret,
                )
            except ValueError as e:
                # Invalid payload
                raise e
            except stripe.error.SignatureVerificationError as e:
                # Invalid signature
                raise e
        else:
            return json.loads(request.body)

    def get_token_from_request(self, payment, request) -> str:
        """Return payment token from provider request."""
        stripe.api_key = self.api_key
        event = self.return_event_payload(request)

        try:
            return event["data"]["object"]["client_reference_id"]
        except Exception as e:
            raise PaymentError(
                code=400,
                message="client_reference_id is not present, check Stripe Dashboard.",
            ) from e

    def process_data(self, payment, request):
        """Processes the event sent by stripe.

        Updates the payment status and adds the event to the attrs property
        """
        event = self.return_event_payload(request)
        if event.get("type") in stripe_enabled_events:
            try:
                session_info = event["data"]["object"]
            except Exception as e:
                raise PaymentError(
                    code=400, message="session not present, check Stripe Dashboard"
                ) from e

            if session_info["status"] == "expired":
                # Expired Order
                payment.change_status(PaymentStatus.REJECTED)

            elif session_info["payment_status"] == "paid":
                # Paid Order
                payment.change_status(PaymentStatus.CONFIRMED)

            payment.attrs.session = session_info
            payment.save()
        return JsonResponse({"status": "OK"})
