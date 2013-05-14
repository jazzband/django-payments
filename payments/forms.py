from django import forms
from django.utils.translation import ugettext_lazy as _

from .fields import CreditCardNumberField, CreditCardExpiryField, CreditCardVerificationField


class PaymentForm(forms.Form):
    '''
    Payment form, suitable for Django templates.

    When displaying the form remeber to use *action* and *method*.
    '''

    #: Form action URL for template use
    action = ''
    #: Form method for template use, either "get" or "post"
    method = 'post'

    def __init__(self, data=None, action=None, method='post', provider=None,
                 payment=None, hidden_inputs=True):
        if hidden_inputs:
            super(PaymentForm, self).__init__(auto_id=False)
            for key, val in data.items():
                widget = forms.widgets.HiddenInput()
                self.fields[key] = forms.CharField(initial=val, widget=widget)
        else:
            super(PaymentForm, self).__init__(data=data)
        self.action = action
        self.method = method
        self.provider = provider
        self.payment = payment


class CreditCardPaymentForm(PaymentForm):

    number = CreditCardNumberField(label=_('Card Number'), max_length=32,
                                   required=True)
    expiration = CreditCardExpiryField()
    cvv2 = CreditCardVerificationField(label=_('CVV2 Security Number'), required=False)

    def __init__(self, *args, **kwargs):
        super(CreditCardPaymentForm, self).__init__(hidden_inputs=False, *args, **kwargs)
        if hasattr(self, 'VALID_TYPES'):
            self.fields['number'].valid_types = self.VALID_TYPES
