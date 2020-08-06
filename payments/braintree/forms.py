import braintree

from ..forms import CreditCardPaymentFormWithName
from .. import PaymentStatus


class BraintreePaymentForm(CreditCardPaymentFormWithName):

    transaction_id = None

    def clean(self):
        data = self.cleaned_data

        if not self.errors and not self.payment.transaction_id:
            result = braintree.Transaction.sale({
                'amount': str(self.payment.total),
                'billing': self.get_billing_data(),
                'credit_card': self.get_credit_card_clean_data(),
                'customer': self.get_customer_data(),
                'options': {
                    'submit_for_settlement': False},
                'order_id': self.payment.description})

            if result.is_success:
                self.transaction_id = result.transaction.id
            else:
                self._errors['__all__'] = self.error_class([result.message])
                self.payment.change_status(PaymentStatus.ERROR)

        return data

    def get_credit_card_clean_data(self):
        if self.cleaned_data:
            return {
                'number': self.cleaned_data.get('number'),
                'cvv': self.cleaned_data.get('cvv2'),
                'cardholder_name': self.cleaned_data.get('name'),
                'expiration_month': self.cleaned_data.get('expiration').month,
                'expiration_year': self.cleaned_data.get('expiration').year}

    def get_billing_data(self):
        return {
            'first_name': self.payment.billing_first_name,
            'last_name': self.payment.billing_last_name,
            'street_address': self.payment.billing_address_1,
            'extended_address': self.payment.billing_address_2,
            'locality': self.payment.billing_city,
            'region': self.payment.billing_country_area,
            'postal_code': self.payment.billing_postcode,
            'country_code_alpha2': self.payment.billing_country_code}

    def get_customer_data(self):
        return {
            'first_name': self.payment.billing_first_name,
            'last_name': self.payment.billing_last_name}

    def save(self):
        braintree.Transaction.submit_for_settlement(self.transaction_id)
        self.payment.transaction_id = self.transaction_id
        self.payment.captured_amount = self.payment.total
        self.payment.change_status(PaymentStatus.CONFIRMED)
