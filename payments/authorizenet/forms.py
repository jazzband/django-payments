from __future__ import unicode_literals

from ..forms import CreditCardPaymentForm

RESPONSE_STATUS = {
    '1': 'confirmed',
    '2': 'rejected'}


class PaymentForm(CreditCardPaymentForm):

    def clean(self):
        cleaned_data = super(PaymentForm, self).clean()

        if not self.errors:
            if not self.payment.transaction_id:
                data = {
                    'x_card_num': cleaned_data.get('number'),
                    'x_exp_date': cleaned_data.get('expiration'),
                    'x_card_code': cleaned_data.get('cvv2')}
                response = self.provider.get_payment_response(
                    self.payment, data)
                data = response.text.split('|')
                if response.ok and RESPONSE_STATUS.get(data[0], False):
                    status = RESPONSE_STATUS.get(data[0], 'error')
                    self.payment.transaction_id = data[6]
                    if status == 'confirmed':
                        self.payment.captured_amount = self.payment.total
                    self.payment.change_status(status)
                else:
                    errors = [data[3]]
                    self._errors['__all__'] = self.error_class(errors)
                    self.payment.change_status('error')
        return cleaned_data
