import json

import stripe
from django import forms
from django.utils.translation import gettext as _

from .. import FraudStatus
from .. import PaymentStatus
from .. import RedirectNeeded
from ..forms import CreditCardPaymentFormWithName
from ..forms import PaymentForm as BasePaymentForm
from ..utils import get_month_choices
from ..utils import get_year_choices
from ..widgets import CreditCardExpiryWidget
from ..widgets import SensitiveSelect
from ..widgets import SensitiveTextInput
from .widgets import StripeCheckoutWidget
from .widgets import StripeWidget


class StripeFormMixin:
    charge = None
    session = None

    def _handle_potentially_fraudulent_charge(self, charge, commit=True):
        # fraud_details = charge["fraud_details"]
        # if fraud_details.get("stripe_report", None) == "fraudulent":
        #     self.payment.change_fraud_status(FraudStatus.REJECT, commit=commit)
        # else:
        #     self.payment.change_fraud_status(FraudStatus.ACCEPT, commit=commit)
        pass

    def clean(self):
        data = self.cleaned_data

        if not self.errors:
            if not self.payment.transaction_id:
                stripe.api_key = self.provider.secret_key
                session_data = {
                    "payment_method_types": self.provider.payment_method_types,
                    "line_items": self.provider.get_line_items(self.payment),
                    "mode": "payment",
                    "success_url": self.payment.get_success_url(),
                    "cancel_url": self.payment.get_failure_url(),
                    "client_reference_id": self.payment.id,
                }
                # Patch session with billing email if exists
                if self.payment.billing_email:
                    session_data.update(
                        {"customer_email": self.payment.billing_email}
                    )
                try:
                    print(f"stripe.checkout.Session.create({session_data=})")
                    self.session = stripe.checkout.Session.create(**session_data)

                except stripe.error.StripeError as e:
                    # Payment has been declined
                    self._errors["__all__"] = self.error_class([str(e)])
                    self.payment.change_status(PaymentStatus.ERROR, str(e))
                else:
                    print(f"{self.session=}")
                    if not self.provider.show_form:
                        raise RedirectNeeded(self.session.get_url)

            else:
                msg = _("This payment has already been processed.")
                self._errors["__all__"] = self.error_class([msg])

        return data

    def save(self):
        self.payment.transaction_id = self.session.id
        self.payment.attrs.session = json.dumps(self.session)
        self.payment.change_status(PaymentStatus.PREAUTH)
        if self.provider._capture:
            self.payment.capture()
        # Make sure we store the info of the charge being marked as fraudulent
        # self._handle_potentially_fraudulent_charge(self.charge)


class ModalPaymentForm(StripeFormMixin, BasePaymentForm):
    def __init__(self, *args, **kwargs):
        print("hello there ModalPaymentForm.__init__")
        super(StripeFormMixin, self).__init__(hidden_inputs=False, *args, **kwargs)
        widget = StripeCheckoutWidget(provider=self.provider, payment=self.payment)
        self.fields["stripeToken"] = forms.CharField(widget=widget)
        if self.is_bound and not self.data.get("stripeToken"):
            self.payment.change_status(PaymentStatus.REJECTED)
            raise RedirectNeeded(self.payment.get_failure_url())


class PaymentForm(StripeFormMixin, BasePaymentForm):
    stripeToken = forms.CharField(widget=StripeWidget())
    session_id = forms.CharField(widget=StripeWidget())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print("hello there PaymentForm.__init__")

        stripe_attrs = self.fields["stripeToken"].widget.attrs
        stripe_attrs["data-publishable-key"] = self.provider.public_key

        session_attrs = self.fields["session_id"].widget.attrs
        session_attrs["data-session-id"] = self.payment.transaction_id
        session_attrs["id"] = "stripe_session_id"

    class Media:
        js = ["https://js.stripe.com/v3", "js/payments/stripe.js"]
