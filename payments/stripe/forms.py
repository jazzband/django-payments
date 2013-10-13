from django import forms

import stripe

from .. import RedirectNeeded
from ..forms import PaymentForm as BasePaymentForm
from .widgets import StripeWidget


class PaymentForm(BasePaymentForm):

    def __init__(self, *args, **kwargs):
        super(PaymentForm, self).__init__(*args, **kwargs)
        widget = StripeWidget(provider=self.provider, payment=self.payment)
        self.fields['stripe_token'] = forms.CharField(widget=widget)

    def save(self):
        data = self.cleaned_data

        stripe.api_key = self.provider.secret_key
        try:
            charge = stripe.Charge.create(
                amount=self.payment.total * 100,
                currency=self.payment.currency,
                card=data['stripe_token'],
                description=u"%s %s" % (self.payment.billing_last_name,
                                        self.payment.billing_first_name)
            )
        except stripe.CardError, e:
            # The card has been declined
            self.payment.change_status('input')
            raise RedirectNeeded(self.payment.get_failure_url())
        else:
            self.payment.transaction_id = charge.id
            self.payment.change_status('confirmed')
            self.payment.save()
