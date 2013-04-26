from ..forms import PaymentForm
from .fields import CreditCardExpiryField, CreditCardNumberField
from django import forms
from django.core import validators
from django.utils.translation import ugettext_lazy as _
from re import match

CVV_VALIDATOR = validators.RegexValidator('^[0-9]{1,4}$',
                                          _('Enter a valid security number.'))


class PaymentForm(PaymentForm):

    VALID_TYPES = ['visa', 'mastercard', 'discover', 'amex']
    name = forms.CharField(label=_('Name on Credit Card'), max_length=128)
    number = CreditCardNumberField(label=_('Card Number'), max_length=32,
                                   required=True)
    expiration = CreditCardExpiryField()
    cvv2 = forms.CharField(validators=[CVV_VALIDATOR], required=False,
                           label=_('CVV2 Security Number'), max_length=4)
    default_error_messages = {
        'invalid_type': _(u'We accept only %(valid_types)s')}

    def __init__(self, *args, **kwargs):
        super(PaymentForm, self).__init__(hidden_inputs=False, *args, **kwargs)

    def get_credit_card_type(self, number):
        if match('^4[0-9]{12}(?:[0-9]{3})?$', number):
            return 'visa'
        if match('^5[1-5][0-9]{14}$', number):
            return 'mastercard'
        if match('^6(?:011|5[0-9]{2})[0-9]{12}$', number):
            return 'discover'
        if match('^3[47][0-9]{13}$', number):
            return 'amex'

    def clean(self):
        cleaned_data = super(PaymentForm, self).clean()
        if 'number' in cleaned_data.keys():
            type = self.get_credit_card_type(cleaned_data['number'])
            if type not in self.VALID_TYPES:
                message = (self.default_error_messages['invalid_type'] %
                           {'valid_types': ', '.join(self.VALID_TYPES)})
                self._errors['number'] = self.error_class([message])
            else:
                cleaned_data['type'] = type
        if not self.errors:
            if not self.payment.transaction_id:
                response = self.provider.get_payment_response(cleaned_data)
                data = response.json()
                if response.ok:
                    self.payment.transaction_id = data['id']
                    self.payment.change_status('confirmed')
                else:
                    errors = [error['issue'] for error in data['details']]
                    self._errors['__all__'] = self.error_class(errors)
                    self.payment.change_status('error')
        return cleaned_data
