from datetime import date
from calendar import monthrange
import re

from django import forms
from django.core import validators
from django.utils.translation import ugettext_lazy as _

from . import widgets

CARD_TYPES = {
    'visa': ('^4[0-9]{12}(?:[0-9]{3})?$', 'VISA'),
    'mastercard': ('^5[1-5][0-9]{14}$', 'MasterCard'),
    'discover': ('^6(?:011|5[0-9]{2})[0-9]{12}$', 'Discover'),
    'amex': ('^3[47][0-9]{13}$', 'American Express'),
    'jcb': ('^(?:(?:2131|1800|35\d{3})\d{11})$', 'JCB'),
    'diners': ('^(?:3(?:0[0-5]|[68][0-9])[0-9]{11})$', 'Diners Club')}


class CreditCard(object):

    def __init__(self, number):
        self.number = number
        self.card_type, self.card_type_fullname = self.get_credit_card_type(number)

    def __repr__(self):
        return 'CreditCard(number=%s, card_type=%s, card_type_fullname=%s)' % \
               (self.number, self.card_type, self.card_type_fullname)

    def __unicode__(self):
        return self.number

    def get_credit_card_type(self, number):
        for card_type, details in CARD_TYPES.items():
            regexp, name = details
            if re.match(regexp, number):
                return card_type, name
        return None, None


class CreditCardNumberField(forms.CharField):

    widget = widgets.CreditCardNumberWidget
    default_error_messages = {
        'invalid': _(u'Please enter a valid card number'),
        'invalid_type': _(u'We accept only %(valid_types)s')}

    def __init__(self, valid_types=None, *args, **kwargs):
        self.valid_types = valid_types
        kwargs['max_length'] = kwargs.pop('max_length', 32)
        super(CreditCardNumberField, self).__init__(*args, **kwargs)

    def to_python(self, value):
        cleaned = re.sub('[\s-]', '', value)
        if value and not cleaned:
            raise forms.ValidationError(self.error_messages['invalid'])
        return CreditCard(number=cleaned)

    def validate(self, card):
        value = card.number
        if value in validators.EMPTY_VALUES and self.required:
            raise forms.ValidationError(self.error_messages['required'])
        if value and not self.cart_number_checksum_validation(value):
            raise forms.ValidationError(self.error_messages['invalid'])
        if value and not self.valid_types is None \
                and not card.card_type in self.valid_types:
            raise forms.ValidationError(self.error_messages['invalid_type'] %
                                        {'valid_types': ', '.join(map(self.get_card_type_fullname,
                                                                      self.valid_types))})

    def run_validators(self, card):
        super(CreditCardNumberField, self).run_validators(card.number)

    def get_card_type_fullname(self, card_type):
            fullname = ''
            type_detail = CARD_TYPES.get(card_type)
            if type_detail:
                _, fullname = type_detail
            return fullname

    def cart_number_checksum_validation(self, number):
        digits = []
        even = False
        if not number.isdigit():
            return False
        for digit in reversed(number):
            digit = ord(digit) - ord('0')
            if even:
                digit = digit * 2
                if digit >= 10:
                    digit = digit % 10 + digit / 10
            digits.append(digit)
            even = not even
        return sum(digits) % 10 == 0 if digits else False


# Credit Card Expiry Fields from:
# http://www.djangosnippets.org/snippets/907/
class CreditCardExpiryWidget(forms.MultiWidget):
    """MultiWidget for representing credit card expiry date."""
    def decompress(self, value):
        if value:
            return [value.month, value.year]
        else:
            return [None, None]

    def format_output(self, rendered_widgets):
        html = u' / '.join(rendered_widgets)
        return u'<span style="white-space: nowrap">%s</span>' % html


# From https://github.com/zen4ever/django-authorizenet
class CreditCardExpiryField(forms.MultiValueField):

    EXP_MONTH = [(x, "%02d" % x) for x in xrange(1, 13)]
    EXP_YEAR = [(x, x) for x in xrange(date.today().year,
                                       date.today().year + 15)]

    default_error_messages = {
        'invalid_month': u'Enter a valid month.',
        'invalid_year': u'Enter a valid year.'}

    def __init__(self, *args, **kwargs):
        errors = self.default_error_messages.copy()
        if 'error_messages' in kwargs:
            errors.update(kwargs['error_messages'])

        fields = (
            forms.ChoiceField(
                choices=self.EXP_MONTH,
                error_messages={'invalid': errors['invalid_month']}),
            forms.ChoiceField(
                choices=self.EXP_YEAR,
                error_messages={'invalid': errors['invalid_year']}),
        )

        super(CreditCardExpiryField, self).__init__(fields, *args, **kwargs)
        self.widget = CreditCardExpiryWidget(widgets=[fields[0].widget,
                                                      fields[1].widget])

    def clean(self, value):
        exp = super(CreditCardExpiryField, self).clean(value)
        if date.today() > exp:
            raise forms.ValidationError(
                "The expiration date you entered is in the past.")
        return exp

    def compress(self, data_list):
        if data_list:
            if data_list[1] in forms.fields.EMPTY_VALUES:
                error = self.error_messages['invalid_year']
                raise forms.ValidationError(error)
            if data_list[0] in forms.fields.EMPTY_VALUES:
                error = self.error_messages['invalid_month']
                raise forms.ValidationError(error)
            year = int(data_list[1])
            month = int(data_list[0])
            # find last day of the month
            day = monthrange(year, month)[1]
            return date(year, month, day)
        return None


class CreditCardVerificationField(forms.CharField):

    default_error_messages = {
        'invalid': _(u'Enter a valid security number.')}

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = kwargs.pop('max_length', 4)
        super(CreditCardVerificationField, self).__init__(*args, **kwargs)

    def validate(self, value):
        if value in validators.EMPTY_VALUES and self.required:
            raise forms.ValidationError(self.error_messages['required'])
        if value and not re.match('^[0-9]{3,4}$', value):
            raise forms.ValidationError(self.error_messages['invalid'])
