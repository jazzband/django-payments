from django import forms
import jwt

from ..forms import PaymentForm as BasePaymentForm
from .widgets import WalletWidget


class PaymentForm(BasePaymentForm):

    def __init__(self, *args, **kwargs):
        super(PaymentForm, self).__init__(*args, **kwargs)
        widget = WalletWidget(provider=self.provider)
        self.fields['payment'] = forms.CharField(widget=widget, required=False)


class ProcessPaymentForm(forms.Form):

    jwt = forms.CharField(required=True)

    def __init__(self, payment, provider, **kwargs):
        super(ProcessPaymentForm, self).__init__(**kwargs)
        self.provider = provider
        self.payment = payment

    def clean_jwt(self):
        payload = super(ProcessPaymentForm, self).clean().get('jwt')
        try:
            jwt_data = jwt.decode(payload.encode('utf-8'),
                                  self.provider.seller_secret)
        except jwt.DecodeError:
            raise forms.ValidationError('Incorrect response')

        if (jwt_data['iss'] != 'Google' or
                jwt_data['aud'] != self.provider.seller_id):
            raise forms.ValidationError('Incorrect response')

        self.token = jwt_data['request']['sellerData']

        if self.payment and self.payment.token != self.token:
            raise forms.ValidationError('Incorrect payment token')

        self.order_id = jwt_data['response']['orderId']
        return payload

    def save(self):
        self.payment.transaction_id = self.order_id
        self.payment.change_status('confirmed')
        self.payment.save()
