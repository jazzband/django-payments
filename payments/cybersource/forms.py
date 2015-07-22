from __future__ import unicode_literals

from uuid import uuid4

from django import forms
from django.template.loader import render_to_string
from django.utils.translation import ugettext as _

from .. import PaymentError
from ..forms import CreditCardPaymentFormWithName


class FingerprintWidget(forms.HiddenInput):

    def render(self, name, value, attrs=None):
        final_attrs = self.build_attrs(attrs, type=self.input_type, name=name)
        final_attrs['session_id'] = value
        return render_to_string(
            'payments/cybersource_fingerprint.html', final_attrs)


class FingerprintInput(forms.CharField):

    widget = FingerprintWidget
    hidden_widget = FingerprintWidget

    def __init__(self, org_id, merchant_id, fingerprint_url,  *args, **kwargs):
        self.org_id = org_id
        self.merchant_id = merchant_id
        self.fingerprint_url = fingerprint_url
        super(FingerprintInput, self).__init__(*args, **kwargs)

    def widget_attrs(self, widget):
        attrs = super(FingerprintInput, self).widget_attrs(widget=widget)
        attrs['org_id'] = self.org_id
        attrs['merchant_id'] = self.merchant_id
        attrs['fingerprint_url'] = self.fingerprint_url
        return attrs


class PaymentForm(CreditCardPaymentFormWithName):

    def __init__(self, *args, **kwargs):
        super(PaymentForm, self).__init__(*args, **kwargs)
        if self.provider.org_id:
            try:
                fingerprint_id = self.payment.attrs.fingerprint_session_id
            except KeyError:
                fingerprint_id = str(uuid4())
            self.fields['fingerprint'] = FingerprintInput(
                label=_('fingerprint'), org_id=self.provider.org_id,
                initial=fingerprint_id,
                merchant_id=self.provider.merchant_id,
                fingerprint_url=self.provider.fingerprint_url)

    def clean(self):
        cleaned_data = super(PaymentForm, self).clean()
        if not self.errors:
            if self.provider.org_id:
                fingerprint = cleaned_data['fingerprint']
                self.payment.attrs.fingerprint_session_id = fingerprint
            if not self.payment.transaction_id:
                try:
                    self.provider.charge(self.payment, cleaned_data)
                except PaymentError as e:
                    self._errors['__all__'] = self.error_class([e.args[0]])
            else:
                msg = _('This payment has already been processed.')
                self._errors['__all__'] = self.error_class([msg])
        return cleaned_data
