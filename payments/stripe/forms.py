from __future__ import unicode_literals

from django import forms
import stripe

from ..forms import PaymentForm as BasePaymentForm
from .widgets import StripeWidget
from . import RedirectNeeded


class PaymentForm(BasePaymentForm):

    charge = None

    def __init__(self, *args, **kwargs):
        super(PaymentForm, self).__init__(*args, **kwargs)
        widget = StripeWidget(provider=self.provider, payment=self.payment)
        self.fields['stripe_token'] = forms.CharField(widget=widget)
        if self.is_bound and not self.data.get('stripe_token'):
            self.payment.change_status('rejected')
            raise RedirectNeeded(self.payment.get_failure_url())

    def clean(self):
        data = self.cleaned_data

        if not self.errors and not self.payment.transaction_id:
            stripe.api_key = self.provider.secret_key
            try:
                self.charge = stripe.Charge.create(
                    capture=False,
                    amount=self.payment.total * 100,
                    currency=self.payment.currency,
                    card=data['stripe_token'],
                    description='%s %s' % (self.payment.billing_last_name,
                                           self.payment.billing_first_name)
                )
            except stripe.CardError as e:
                # The card has been declined
                self._errors['__all__'] = self.error_class([e.message])
                self.payment.change_status('error')

        return data

    def save(self):
        self.charge.capture()
        self.payment.transaction_id = self.charge.id
        self.payment.change_status('confirmed')
