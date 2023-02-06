from requests.exceptions import HTTPError

from .. import PaymentStatus
from ..core import get_credit_card_issuer
from ..forms import CreditCardPaymentFormWithName


class PaymentForm(CreditCardPaymentFormWithName):
    VALID_TYPES = ["visa", "mastercard", "discover", "amex"]

    def clean(self):
        cleaned_data = super().clean()

        if not self.errors:
            if not self.payment.transaction_id:
                number = cleaned_data.get("number")
                card_type, _card_issuer = get_credit_card_issuer(number)
                request_data = {"type": card_type}
                request_data.update(cleaned_data)
                try:
                    data = self.provider.create_payment(self.payment, cleaned_data)
                except HTTPError as e:
                    response = e.response
                    if response.status_code == 400:
                        error_data = e.response.json()
                        errors = [error["issue"] for error in error_data["details"]]
                    else:
                        errors = ["Internal PayPal error"]
                    self._errors["__all__"] = self.error_class(errors)
                    self.payment.change_status(PaymentStatus.ERROR)
                else:
                    self.payment.transaction_id = data["id"]
                    self.provider.set_response_links(self.payment, data)
                    if self.provider._capture:
                        self.payment.captured_amount = self.payment.total
                        self.payment.change_status(PaymentStatus.CONFIRMED)
                    else:
                        self.payment.change_status(PaymentStatus.PREAUTH)
        return cleaned_data
