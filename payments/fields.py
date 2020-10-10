from calendar import monthrange
from datetime import date
import re

from django import forms
from django.core import validators
from django.utils.translation import gettext_lazy as _

from .core import get_credit_card_issuer
from .utils import get_month_choices, get_year_choices
from .widgets import CreditCardExpiryWidget, CreditCardNumberWidget


class CreditCardNumberField(forms.CharField):

    widget = CreditCardNumberWidget(
        attrs={'autocomplete': 'cc-number', 'required': 'required'})
    default_error_messages = {
        'invalid': _('Please enter a valid card number'),
        'invalid_type': _('We accept only %(valid_types)s')}

    def __init__(self, valid_types=None, *args, **kwargs):
        self.valid_types = valid_types
        kwargs['max_length'] = kwargs.pop('max_length', 32)
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value is not None:
            value = re.sub(r'[\s-]+', '', value)
        return super().to_python(value)

    def validate(self, value):
        card_type, issuer_name = get_credit_card_issuer(value)
        if value in validators.EMPTY_VALUES and self.required:
            raise forms.ValidationError(self.error_messages['required'])
        if value and not self.cart_number_checksum_validation(self, value):
            raise forms.ValidationError(self.error_messages['invalid'])
        if (value and not self.valid_types is None
                and not card_type in self.valid_types):
            valid_types = map(issuer_name, self.valid_types)
            error_message = self.error_messages['invalid_type'] % {
                'valid_types': ', '.join(valid_types)
            }
            raise forms.ValidationError(error_message)

    @staticmethod
    def cart_number_checksum_validation(cls, number):
        digits = []
        even = False
        if not number.isdigit():
            return False
        for digit in reversed(number):
            digit = ord(digit) - ord('0')
            if even:
                digit *= 2
                if digit >= 10:
                    digit = digit % 10 + digit // 10
            digits.append(digit)
            even = not even
        return sum(digits) % 10 == 0 if digits else False



class CreditCardExpiryField(forms.MultiValueField):

    default_error_messages = {
        'invalid_month': 'Enter a valid month.',
        'invalid_year': 'Enter a valid year.'}

    def __init__(self, *args, **kwargs):
        errors = self.default_error_messages.copy()
        if 'error_messages' in kwargs:
            errors.update(kwargs['error_messages'])

        fields = (
            forms.ChoiceField(
                choices=get_month_choices(),
                error_messages={'invalid': errors['invalid_month']},
                widget=forms.Select(
                    attrs={'autocomplete': 'cc-exp-month',
                           'required': 'required'})),
            forms.ChoiceField(
                choices=get_year_choices(),
                error_messages={'invalid': errors['invalid_year']},
                widget=forms.Select(
                    attrs={'autocomplete': 'cc-exp-year',
                           'required': 'required'})),
        )

        super().__init__(fields, *args, **kwargs)
        self.widget = CreditCardExpiryWidget(widgets=[fields[0].widget,
                                                      fields[1].widget])

    def clean(self, value):
        exp = super().clean(value)
        if exp and date.today() > exp:
            raise forms.ValidationError(
                "The expiration date you entered is in the past.")
        return exp

    def compress(self, data_list):
        if data_list:
            if data_list[1] in validators.EMPTY_VALUES:
                error = self.error_messages['invalid_year']
                raise forms.ValidationError(error)
            if data_list[0] in validators.EMPTY_VALUES:
                error = self.error_messages['invalid_month']
                raise forms.ValidationError(error)
            year = int(data_list[1])
            month = int(data_list[0])
            # find last day of the month
            day = monthrange(year, month)[1]
            return date(year, month, day)
        return None


class CreditCardVerificationField(forms.CharField):

    widget = forms.TextInput(
        attrs={'autocomplete': 'cc-csc'})
    default_error_messages = {
        'invalid': _('Enter a valid security number.')}

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = kwargs.pop('max_length', 4)
        super().__init__(*args, **kwargs)

    def validate(self, value):
        if value in validators.EMPTY_VALUES and self.required:
            raise forms.ValidationError(self.error_messages['required'])
        if value and not re.match('^[0-9]{3,4}$', value):
            raise forms.ValidationError(self.error_messages['invalid'])


class CreditCardNameField(forms.CharField):

    widget = forms.TextInput(
        attrs={'autocomplete': 'cc-name', 'required': 'required'})
