from __future__ import unicode_literals

from django.utils.translation import ugettext as _

from .. import PaymentError
from ..forms import CreditCardPaymentFormWithName


class PaymentForm(CreditCardPaymentFormWithName):

    def clean(self):
        cleaned_data = super(PaymentForm, self).clean()
        if not self.errors:
            if not self.payment.transaction_id:
                try:
                    self.provider.charge(cleaned_data)
                except PaymentError as e:
                    self._errors['__all__'] = self.error_class([e.args[0]])
            else:
                msg = _('This payment has already been processed.')
                self._errors['__all__'] = self.error_class([msg])
        return cleaned_data
