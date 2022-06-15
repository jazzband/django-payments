from .. import PaymentStatus
from ..forms import CreditCardPaymentForm

RESPONSE_STATUS = {
    "1": PaymentStatus.CONFIRMED,
    "2": PaymentStatus.REJECTED,
}


class PaymentForm(CreditCardPaymentForm):
    def clean(self):
        cleaned_data = super().clean()

        if not self.errors:
            if not self.payment.transaction_id:
                data = {
                    "x_card_num": cleaned_data.get("number"),
                    "x_exp_date": cleaned_data.get("expiration"),
                    "x_card_code": cleaned_data.get("cvv2"),
                }
                response = self.provider.get_payment_response(self.payment, data)

                data = response.text.split("|")
                status = "error"
                message = data[3]
                if response.ok and RESPONSE_STATUS.get(data[0], False):
                    status = RESPONSE_STATUS.get(data[0], status)
                    self.payment.transaction_id = data[6]
                    self.payment.change_status(status, message=message)
                    if status == PaymentStatus.CONFIRMED:
                        self.payment.captured_amount = self.payment.total
                        return cleaned_data
                    self.payment.change_status(status)

                errors = [data[3]]
                self._errors["__all__"] = self.error_class(errors)
                self.payment.change_status(PaymentStatus.ERROR)
        return cleaned_data
