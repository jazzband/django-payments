from collections import OrderedDict

from django import forms
from django.utils.translation import gettext_lazy as _

from .fields import CreditCardExpiryField
from .fields import CreditCardNameField
from .fields import CreditCardNumberField
from .fields import CreditCardVerificationField


class PaymentForm(forms.Form):
    '''
    Payment form, suitable for Django templates.

    When displaying the form remember to use *action* and *method*.
    '''
    def __init__(self, data=None, action='', method='post', provider=None,
                 payment=None, hidden_inputs=True, autosubmit=False):
        if hidden_inputs and data is not None:
            super().__init__(auto_id=False)
            for key, val in data.items():
                widget = forms.widgets.HiddenInput()
                self.fields[key] = forms.CharField(initial=val, widget=widget)
        else:
            super().__init__(data=data)
        self.action = action
        self.autosubmit = autosubmit
        self.method = method
        self.provider = provider
        self.payment = payment


class CreditCardPaymentForm(PaymentForm):

    number = CreditCardNumberField(label=_('Card Number'), max_length=32,
                                   required=True)
    expiration = CreditCardExpiryField()
    cvv2 = CreditCardVerificationField(
        label=_('CVV2 Security Number'), required=False, help_text=_(
            'Last three digits located on the back of your card.'
            ' For American Express the four digits found on the front side.'))

    def __init__(self, *args, **kwargs):
        super().__init__(
            hidden_inputs=False, *args, **kwargs)
        if hasattr(self, 'VALID_TYPES'):
            self.fields['number'].valid_types = self.VALID_TYPES


class CreditCardPaymentFormWithName(CreditCardPaymentForm):

    name = CreditCardNameField(label=_('Name on Credit Card'), max_length=128)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        name_field = self.fields.pop('name')
        fields = OrderedDict({'name': name_field})
        fields.update(self.fields)
        self.fields = fields
