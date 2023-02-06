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

    def _handle_potentially_fraudulent_charge(self, charge, commit=True):
        fraud_details = charge["fraud_details"]
        if fraud_details.get("stripe_report", None) == "fraudulent":
            self.payment.change_fraud_status(FraudStatus.REJECT, commit=commit)
        else:
            self.payment.change_fraud_status(FraudStatus.ACCEPT, commit=commit)

    def clean(self):
        data = self.cleaned_data

        if not self.errors:
            if not self.payment.transaction_id:
                stripe.api_key = self.provider.secret_key
                try:
                    charge_data = {
                        "capture": False,
                        "amount": int(self.payment.total * 100),
                        "currency": self.payment.currency,
                        "card": data["stripeToken"],
                        "description": "{} {}".format(
                            self.payment.billing_last_name,
                            self.payment.billing_first_name,
                        ),
                        "metadata": self.payment.order.get_metadata(),
                    }

                    # Patch charge with billing email if exists
                    if self.payment.billing_email:
                        charge_data.update(
                            {
                                "receipt_email": self.payment.billing_email,
                            }
                        )

                    self.charge = stripe.Charge.create(**charge_data)

                except stripe.error.CardError as e:
                    # Making sure we retrieve the charge
                    charge_id = e.json_body["error"]["charge"]
                    self.charge = stripe.Charge.retrieve(charge_id)
                    # Checking if the charge was fraudulent
                    self._handle_potentially_fraudulent_charge(
                        self.charge, commit=False
                    )
                    # The card has been declined
                    self._errors["__all__"] = self.error_class([str(e)])
                    self.payment.change_status(PaymentStatus.ERROR, str(e))
            else:
                msg = _("This payment has already been processed.")
                self._errors["__all__"] = self.error_class([msg])

        return data

    def save(self):
        self.payment.transaction_id = self.charge.id
        self.payment.attrs.charge = json.dumps(self.charge)
        self.payment.change_status(PaymentStatus.PREAUTH)
        if self.provider._capture:
            self.payment.capture()
        # Make sure we store the info of the charge being marked as fraudulent
        self._handle_potentially_fraudulent_charge(self.charge)


class ModalPaymentForm(StripeFormMixin, BasePaymentForm):
    def __init__(self, *args, **kwargs):
        super(StripeFormMixin, self).__init__(hidden_inputs=False, *args, **kwargs)
        widget = StripeCheckoutWidget(provider=self.provider, payment=self.payment)
        self.fields["stripeToken"] = forms.CharField(widget=widget)
        if self.is_bound and not self.data.get("stripeToken"):
            self.payment.change_status(PaymentStatus.REJECTED)
            raise RedirectNeeded(self.payment.get_failure_url())


class PaymentForm(StripeFormMixin, CreditCardPaymentFormWithName):
    stripeToken = forms.CharField(widget=StripeWidget())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        stripe_attrs = self.fields["stripeToken"].widget.attrs
        stripe_attrs["data-publishable-key"] = self.provider.public_key
        stripe_attrs["data-address-line1"] = self.payment.billing_address_1
        stripe_attrs["data-address-line2"] = self.payment.billing_address_2
        stripe_attrs["data-address-city"] = self.payment.billing_city
        stripe_attrs["data-address-state"] = self.payment.billing_country_area
        stripe_attrs["data-address-zip"] = self.payment.billing_postcode
        stripe_attrs["data-address-country"] = self.payment.billing_country_code
        widget_map = {
            "name": SensitiveTextInput(
                attrs={"autocomplete": "cc-name", "required": "required"}
            ),
            "cvv2": SensitiveTextInput(attrs={"autocomplete": "cc-csc"}),
            "number": SensitiveTextInput(
                attrs={"autocomplete": "cc-number", "required": "required"}
            ),
            "expiration": CreditCardExpiryWidget(
                widgets=[
                    SensitiveSelect(
                        attrs={"autocomplete": "cc-exp-month", "required": "required"},
                        choices=get_month_choices(),
                    ),
                    SensitiveSelect(
                        attrs={"autocomplete": "cc-exp-year", "required": "required"},
                        choices=get_year_choices(),
                    ),
                ]
            ),
        }
        for field_name, widget in widget_map.items():
            self.fields[field_name].widget = widget
            self.fields[field_name].required = False
