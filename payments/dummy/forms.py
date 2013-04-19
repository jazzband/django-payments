from ..forms import PaymentForm
from django import forms
from django.utils.translation import ugettext_lazy as _


class DummyForm(PaymentForm):

    name = forms.CharField(label=_('Name on Credit Card'), max_length=128)
    number = forms.CharField(label=_('Card Number'), max_length=32)
    expiration = forms.CharField(max_length=5)
    cvv2 = forms.CharField(required=False, label=_('CVV2 Security Number'),
                           max_length=4)

    def clean(self):
        cleaned_data = super(DummyForm, self).clean()
        if not self.errors:
            cleaned_data['next'] = self.payment.get_success_url()
            self.payment.change_status('confirmed')
        return cleaned_data
