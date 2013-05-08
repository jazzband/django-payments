from re import match

from django import forms
from django.core import validators
from django.utils.translation import ugettext_lazy as _

from .fields import CreditCardNumberField, CreditCardExpiryField


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

    CVV_VALIDATOR = validators.RegexValidator('^[0-9]{1,4}$',
                                              _('Enter a valid security number.'))

    number = CreditCardNumberField(label=_('Card Number'), max_length=32,
                                   required=True)
    expiration = CreditCardExpiryField()
    cvv2 = forms.CharField(validators=[CVV_VALIDATOR], required=False,
                           label=_('CVV2 Security Number'), max_length=4)

    default_error_messages = {
        'invalid_type': _(u'We accept only %(valid_types)s')}

    def __init__(self, *args, **kwargs):
        super(CreditCardPaymentForm, self).__init__(hidden_inputs=False, *args, **kwargs)

    def get_credit_card_type(self, number):
        if match('^4[0-9]{12}(?:[0-9]{3})?$', number):
            return 'visa'
        if match('^5[1-5][0-9]{14}$', number):
            return 'mastercard'
        if match('^6(?:011|5[0-9]{2})[0-9]{12}$', number):
            return 'discover'
        if match('^3[47][0-9]{13}$', number):
            return 'amex'
        if match('^(?:(?:2131|1800|35\d{3})\d{11})$', number):
            return 'jcb'
        if match('^(?:3(?:0[0-5]|[68][0-9])[0-9]{11})$', number):
            return 'diners club'

    def clean(self):
        cleaned_data = super(PaymentForm, self).clean()

        if 'number' in cleaned_data.keys():
            card_type = self.get_credit_card_type(cleaned_data['number'])
            if card_type not in self.VALID_TYPES:
                message = (self.default_error_messages['invalid_type'] %
                           {'valid_types': ', '.join(self.VALID_TYPES)})
                self._errors['number'] = self.error_class([message])
            else:
                self.card_type = card_type

        return cleaned_data
