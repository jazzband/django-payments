from django import forms

from ..forms import PaymentForm as BasePaymentForm
from ..widgets import WalletWidget


class PaymentForm(BasePaymentForm):

    def __init__(self, *args, **kwargs):
        super(PaymentForm, self).__init__(*args, **kwargs)
        self.fields['payment'] = forms.CharField(widget=WalletWidget(provider=self.provider), required=False)
