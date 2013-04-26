from ..forms import PaymentForm
from django import forms
from django.utils.translation import ugettext_lazy as _


class DummyForm(PaymentForm):

    name = forms.CharField(label=_('Name on Credit Card'), max_length=128)
    number = forms.CharField(label=_('Card Number'), max_length=32)
    expiration = forms.CharField(max_length=5)
    cvv2 = forms.CharField(required=False, label=_('CVV2 Security Number'),
                           max_length=4)
