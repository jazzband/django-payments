from __future__ import unicode_literals

from django import forms
from django.utils.translation import ugettext as _
import stripe

from .widgets import StripeCheckoutWidget, StripeWidget
from .. import RedirectNeeded
from ..forms import PaymentForm as BasePaymentForm, CreditCardPaymentFormWithName
from ..models import FRAUD_CHOICES


class StripeFormMixin(object):

    charge = None

    def _handle_potentially_fraudulent_charge(self, charge, commit=True):
        fraud_details = charge['fraud_details']
        if fraud_details.get('stripe_report', None) == 'fraudulent':
            reject_fraud_choice = FRAUD_CHOICES[2][0]
            self.payment.change_fraud_status(
                reject_fraud_choice, commit=commit)
        else:
            accept_fraud_choice = FRAUD_CHOICES[1][0]
            self.payment.change_fraud_status(
                accept_fraud_choice, commit=commit)

    def clean(self):
        data = self.cleaned_data

        if not self.errors:
            if not self.payment.transaction_id:
                stripe.api_key = self.provider.secret_key
                try:
                    self.charge = stripe.Charge.create(
                        capture=False,
                        amount=int(self.payment.total * 100),
                        currency=self.payment.currency,
                        card=data['stripeToken'],
                        description='%s %s' % (
                            self.payment.billing_last_name,
                            self.payment.billing_first_name))
                except stripe.CardError as e:
                    # Making sure we retrieve the charge
                    charge_id = e.json_body['error']['charge']
                    self.charge = stripe.Charge.retrieve(charge_id)
                    # Checking if the charge was fraudulent
                    self._handle_potentially_fraudulent_charge(
                        self.charge, commit=False)
                    # The card has been declined
                    self._errors['__all__'] = self.error_class([str(e)])
                    self.payment.change_status('error', str(e))
            else:
                msg = _('This payment has already been processed.')
                self._errors['__all__'] = self.error_class([msg])

        return data

    def save(self):
        self.charge.capture()
        # Make sure we store the info of the charge being marked as fraudulent
        self._handle_potentially_fraudulent_charge(
            self.charge, commit=False)
        self.payment.transaction_id = self.charge.id
        self.payment.captured_amount = self.payment.total
        self.payment.change_status('confirmed')


class ModalPaymentForm(StripeFormMixin, BasePaymentForm):

    def __init__(self, *args, **kwargs):
        super(StripeFormMixin, self).__init__(*args, **kwargs)
        widget = StripeCheckoutWidget(provider=self.provider, payment=self.payment)
        self.fields['stripeToken'] = forms.CharField(widget=widget)
        if self.is_bound and not self.data.get('stripeToken'):
            self.payment.change_status('rejected')
            raise RedirectNeeded(self.payment.get_failure_url())


class PaymentForm(StripeFormMixin, CreditCardPaymentFormWithName):

    stripeToken = forms.CharField(widget=StripeWidget())

    def __init__(self, *args, **kwargs):
        super(PaymentForm, self).__init__(*args, **kwargs)
        stripe_attrs = self.fields['stripeToken'].widget.attrs
        stripe_attrs['data-publishable-key'] = self.provider.public_key
        stripe_attrs['data-address-line1'] = self.payment.billing_address_1
        stripe_attrs['data-address-line2'] = self.payment.billing_address_2
        stripe_attrs['data-address-city'] = self.payment.billing_city
        stripe_attrs['data-address-state'] = self.payment.billing_country_area
        stripe_attrs['data-address-zip'] = self.payment.billing_postcode
        stripe_attrs['data-address-country'] = self.payment.billing_country_code
