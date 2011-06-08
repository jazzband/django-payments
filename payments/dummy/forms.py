from django import forms
from django.core.urlresolvers import reverse
from ..models import PAYMENT_STATUS_CHOICES

class DummyPaymentForm(forms.Form):
    method = 'post'
    def action(self):
        return reverse('process_payment', args=[self.variant])
    action = property(action)

    def __init__(self, variant, *args, **kwargs):
        self.variant = variant
        return super(DummyPaymentForm, self).__init__(*args, **kwargs)

    payment_id = forms.IntegerField(widget=forms.HiddenInput())
    status = forms.ChoiceField(choices=PAYMENT_STATUS_CHOICES)

class DummyRedirectForm(forms.Form):
    method = 'post'
    def action(self):
        return reverse('process_payment', args=[self.variant])
    action = property(action)

    def __init__(self, variant, *args, **kwargs):
        self.variant = variant
        return super(DummyRedirectForm, self).__init__(*args, **kwargs)

    payment_id = forms.IntegerField(widget=forms.HiddenInput())

