from __future__ import annotations

import json
import logging
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from urllib.parse import urljoin

import stripe
from django.db import transaction
from django.http import JsonResponse

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded
from payments.core import BasicProvider
from payments.core import get_base_url
from payments.forms import PaymentForm as BasePaymentForm

logger = logging.getLogger(__name__)


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
    "setup_intent.succeeded",  # For zero-dollar auth (card changes)
]


class StripeProviderV3(BasicProvider):
    """Provider backend using `Stripe <https://stripe.com/>`_ api version 3.

    :param api_key: Secret key assigned by Stripe.
    :param use_token: Use instance.token instead of instance.pk in client_reference_id
    :param endpoint_secret: Endpoint Signing Secret.
    :param secure_endpoint: Validate the recieved data, useful for development.
    :param recurring_payments: Enable wallet-based recurring payments
        (server-initiated).
    :param store_payment_method: Store PaymentMethod for future use
        (auto-enabled if recurring_payments=True).
    :param use_setup_mode: Use setup mode (for zero-dollar auth / card changes).
        Creates SetupIntent instead of PaymentIntent. Mutually exclusive with
        regular payments.
    """

    form_class = BasePaymentForm

    def __init__(
        self,
        api_key,
        use_token=True,
        endpoint_secret=None,
        secure_endpoint=True,
        recurring_payments=False,
        store_payment_method=False,
        use_setup_mode=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.use_token = use_token
        self.endpoint_secret = endpoint_secret
        self.secure_endpoint = secure_endpoint
        self.recurring_payments = recurring_payments
        self.use_setup_mode = use_setup_mode
        self.store_payment_method = (
            store_payment_method or recurring_payments or use_setup_mode
        )

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
                "success_url": urljoin(get_base_url(), payment.get_success_url()),
                "cancel_url": urljoin(get_base_url(), payment.get_failure_url()),
                "client_reference_id": payment.token if self.use_token else payment.pk,
            }

            if self.use_setup_mode:
                # Setup mode for zero-dollar auth (card changes)
                # Collects payment method without charging
                session_data["mode"] = "setup"
                session_data["currency"] = payment.currency.lower()

                # Reuse existing customer if available
                renew_data = payment.get_renew_data()
                if renew_data and renew_data.get("customer_id"):
                    session_data["customer"] = renew_data["customer_id"]
                else:
                    # Force customer creation
                    session_data["customer_creation"] = "always"

                # Configure setup intent for future use
                session_data["setup_intent_data"] = {
                    "metadata": {"payment_id": str(payment.pk)},
                }
            else:
                # Payment mode for normal payments
                session_data["mode"] = "payment"
                session_data["line_items"] = self.get_line_items(payment)

                # Enable payment method storage for recurring payments
                if self.store_payment_method:
                    session_data["payment_intent_data"] = {
                        "setup_future_usage": "off_session",
                    }

                    # Reuse existing customer if available (from previous payment)
                    renew_data = payment.get_renew_data()
                    if renew_data and renew_data.get("customer_id"):
                        session_data["customer"] = renew_data["customer_id"]
                    else:
                        # Force customer creation for new subscriptions
                        # This ensures PaymentMethod is attached to a customer
                        session_data["customer_creation"] = "always"

            # Patch session with billing email if exists (only if no customer set)
            if payment.billing_email and "customer" not in session_data:
                session_data.update({"customer_email": payment.billing_email})

            # Store billing name and address in metadata for audit trail
            # Note: We rely on Stripe's default billing_address_collection="auto"
            # which only collects address when needed for tax/compliance.
            # The metadata below is stored for audit trail regardless.
            metadata = {}
            if payment.billing_first_name or payment.billing_last_name:
                metadata["customer_name"] = (
                    f"{payment.billing_first_name} {payment.billing_last_name}".strip()
                )
            if payment.billing_address_1:
                metadata["billing_address_1"] = payment.billing_address_1
            if payment.billing_address_2:
                metadata["billing_address_2"] = payment.billing_address_2
            if payment.billing_city:
                metadata["billing_city"] = payment.billing_city
            if payment.billing_postcode:
                metadata["billing_postcode"] = payment.billing_postcode
            if payment.billing_country_code:
                metadata["billing_country_code"] = payment.billing_country_code
            if payment.billing_country_area:
                metadata["billing_country_area"] = payment.billing_country_area
            if payment.billing_phone:
                metadata["billing_phone"] = str(payment.billing_phone)

            if metadata:
                session_data["metadata"] = metadata
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

        # Add description if available
        if payment.description:
            product_data.description = payment.description

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
        event_type = event.get("type")

        # checkout.session events have client_reference_id
        if event_type and event_type.startswith("checkout.session"):
            try:
                return event["data"]["object"]["client_reference_id"]
            except Exception as e:
                raise PaymentError(
                    code=400,
                    message=(
                        "client_reference_id is not present in checkout.session event."
                    ),
                ) from e

        # payment_intent events don't have client_reference_id
        # These are follow-up webhooks - we already processed the payment
        # in checkout.session. Return None to signal skip by static_callback
        return None

    def autocomplete_with_wallet(self, payment):
        """
        Complete payment using stored PaymentMethod (server-initiated).

        This method charges a stored payment method without user interaction.
        Uses get_renew_data() to retrieve both payment_method_id and customer_id.

        If 3D Secure or other authentication is required, raises RedirectNeeded.
        """
        stripe.api_key = self.api_key

        # Get renew data (payment method and customer ID)
        renew_data = payment.get_renew_data()
        if not renew_data or not renew_data.get("token"):
            raise PaymentError("No payment method token found for recurring payment")

        payment_method_id = renew_data["token"]
        customer_id = renew_data.get("customer_id")

        if not customer_id:
            raise PaymentError(
                "No customer_id found for recurring payment. "
                "Customer ID must be stored during first payment setup."
            )

        try:
            # Create PaymentIntent with customer (required for off_session)
            intent_params = {
                "amount": self.convert_amount(payment.currency, payment.total),
                "currency": payment.currency.lower(),
                "customer": customer_id,  # Required for off_session
                "payment_method": payment_method_id,
                "confirm": True,
                "off_session": True,
                "metadata": {
                    "payment_token": payment.token,
                    "payment_id": payment.pk if not self.use_token else None,
                },
            }

            # Add description if available (visible in Stripe Dashboard)
            if payment.description:
                intent_params["description"] = payment.description

            intent = stripe.PaymentIntent.create(**intent_params)

            payment.transaction_id = intent.id
            payment.attrs.payment_intent = intent
            payment.save()

            # Handle PaymentIntent status
            self._handle_payment_intent_status(payment, intent)

        except stripe.error.CardError as e:
            # Card was declined
            payment.change_status(PaymentStatus.REJECTED, str(e))
            raise PaymentError(f"Card declined: {e}") from e

        except stripe.error.StripeError as e:
            # Other Stripe error
            payment.change_status(PaymentStatus.ERROR, str(e))
            raise PaymentError(f"Stripe error: {e}") from e

    def _handle_payment_intent_status(self, payment, intent):
        """
        Handle PaymentIntent status and update payment accordingly.

        Args:
            payment: Payment instance to update
            intent: Stripe PaymentIntent object

        Raises:
            RedirectNeeded: If 3D Secure authentication is required
        """
        if intent.status == "succeeded":
            payment.captured_amount = payment.total
            payment.change_status(PaymentStatus.CONFIRMED)
            self._finalize_wallet_payment(payment)

        elif intent.status == "requires_action":
            # 3D Secure or other authentication needed
            if intent.next_action and intent.next_action.type == "redirect_to_url":
                redirect_url = intent.next_action.redirect_to_url.url
                raise RedirectNeeded(redirect_url)
            raise PaymentError(f"Payment requires action: {intent.next_action}")

        elif intent.status in ["requires_payment_method", "canceled"]:
            # Payment failed
            error_message = "Payment failed"
            if intent.last_payment_error:
                error_message = intent.last_payment_error.message
            payment.change_status(PaymentStatus.REJECTED, error_message)

        else:
            # Other status (processing, requires_capture, etc.)
            payment.change_status(PaymentStatus.WAITING)

    def erase_wallet(self, wallet):
        """
        Erase Stripe payment method by detaching from customer.

        Stripe doesn't require explicit deletion - PaymentMethods are automatically
        cleaned up when not used. However, we detach it from the customer for clarity
        and to prevent accidental reuse.

        Args:
            wallet: BaseWallet instance to erase
        """
        stripe.api_key = self.api_key

        renew_data = wallet.extra_data if hasattr(wallet, "extra_data") else {}
        payment_method_id = wallet.token
        customer_id = renew_data.get("customer_id")

        if payment_method_id and customer_id:
            try:
                # Detach PaymentMethod from customer
                stripe.PaymentMethod.detach(payment_method_id)
            except stripe.error.StripeError as e:
                # Log but don't fail - wallet is already marked ERASED
                logger.warning(
                    "Failed to detach Stripe PaymentMethod %s: %s",
                    payment_method_id,
                    e,
                )

        # Call parent to mark wallet as ERASED
        super().erase_wallet(wallet)

    def _is_session_complete(self, session_info):
        """Check if Checkout Session is complete (payment or setup mode)."""
        # Setup mode (zero-dollar): check setup_intent status
        if session_info.get("mode") == "setup":
            setup_intent_id = session_info.get("setup_intent")
            if setup_intent_id:
                stripe.api_key = self.api_key
                setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)
                return setup_intent.status == "succeeded"
            return False

        # Payment mode: check payment_status
        return session_info.get("payment_status") == "paid"

    def _store_payment_method_from_session(self, payment, session_info):
        """
        Extract and store PaymentMethod and Customer from Checkout Session.

        Called after payment is confirmed to store payment method for future
        recurring charges. Handles both PaymentIntent (payment mode) and
        SetupIntent (setup mode for zero-dollar auth).
        """
        stripe.api_key = self.api_key

        try:
            # Check if this is setup mode (zero-dollar) or payment mode
            if session_info.get("mode") == "setup":
                # Setup mode: Get SetupIntent
                setup_intent_id = session_info.get("setup_intent")
                if not setup_intent_id:
                    return

                setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)
                payment_method_id = setup_intent.payment_method
                customer_id = setup_intent.customer
            else:
                # Payment mode: Get PaymentIntent
                payment_intent_id = session_info.get("payment_intent")
                if not payment_intent_id:
                    return

                payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                payment_method_id = payment_intent.payment_method
                customer_id = payment_intent.customer

            if not payment_method_id:
                return

            # Get PaymentMethod details for card info
            payment_method = stripe.PaymentMethod.retrieve(payment_method_id)

            # Extract card details
            card_data = {}
            if payment_method.type == "card" and payment_method.card:
                card_data = {
                    "card_expire_year": payment_method.card.exp_year,
                    "card_expire_month": payment_method.card.exp_month,
                    "card_masked_number": payment_method.card.last4,
                }

            # Store payment method token and customer ID
            payment.set_renew_token(
                token=payment_method_id,
                customer_id=customer_id,
                **card_data,
            )

        except stripe.error.StripeError as e:
            # Failed to retrieve payment method, but payment was successful
            # Don't fail the payment, just log the error
            logger.exception(
                "Failed to store PaymentMethod for payment %s: %s", payment.id, e
            )

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

            elif self._is_session_complete(session_info):
                # Store PaymentMethod BEFORE changing status
                # This is important because status change triggers signal that
                # sets token_verified=True. Use atomic transaction to prevent
                # race conditions with concurrent webhooks
                with transaction.atomic():
                    if self.store_payment_method and hasattr(
                        payment, "set_renew_token"
                    ):
                        self._store_payment_method_from_session(payment, session_info)

                    # Now change status (triggers signal that sets token_verified=True)
                    payment.change_status(PaymentStatus.CONFIRMED)

            payment.attrs.session = session_info
            payment.save()
        return JsonResponse({"status": "OK"})
