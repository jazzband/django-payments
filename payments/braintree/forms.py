import braintree
from ..forms import CreditCardPaymentForm as BaseCreditCardPaymentForm


class BraintreePaymentForm(BaseCreditCardPaymentForm):

    def save(self):
        data = self.cleaned_data

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
            self.payment.save()
