import braintree

from ..forms import CreditCardPaymentForm as BaseCreditCardPaymentForm


class BraintreePaymentForm(BaseCreditCardPaymentForm):

    def clean(self):
        data = self.cleaned_data

        if not self.errors and not self.payment.transaction_id:
            result = braintree.Transaction.sale({
                "amount": self.payment.total,
                "credit_card": {
                    "number": data.get("number").number,
                    "cvv": data.get('cvv2'),
                    "expiration_month": data.get('expiration').month,
                    "expiration_year": data.get('expiration').year
                },
                "options": {
                    "submit_for_settlement": True
                }
            })

            if result.is_success:
                self.payment.transaction_id = result.transaction.id
                self.payment.change_status('confirmed')
            else:
                self._errors['__all__'] = self.error_class([result.message])
                self.payment.change_status('error')

        return data
