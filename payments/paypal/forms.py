from django import forms
from django.utils.translation import ugettext_lazy as _

from ..forms import CreditCardPaymentFormWithName
from .. import get_credit_card_issuer


class PaymentForm(CreditCardPaymentFormWithName):

    VALID_TYPES = ['visa', 'mastercard', 'discover', 'amex']

    def clean(self):
        cleaned_data = super(PaymentForm, self).clean()

        if not self.errors:
            if not self.payment.transaction_id:
                number = cleaned_data.get('number')
                card_type, _card_issuer = get_credit_card_issuer(number)
                request_data = {'type': card_type}
                request_data.update(cleaned_data)
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
