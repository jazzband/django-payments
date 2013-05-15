import time

from django.http import HttpResponseForbidden, HttpResponse
import jwt

from .. import get_payment_model, BasicProvider
from .forms import PaymentForm, ProcessPaymentForm

Payment = get_payment_model()


class GoogleWalletProvider(BasicProvider):

    def __init__(self, *args, **kwargs):
        self.merchant_id = kwargs.pop('merchant_id')
        self.merchant_secret = kwargs.pop('merchant_secret')
        self.library = kwargs.pop('library', 'https://sandbox.google.com/checkout/inapp/lib/buy.js')
        super(GoogleWalletProvider, self).__init__(*args, **kwargs)

    def get_jwt_data(self):

        current_time = int(time.time())
        exp_time = current_time + 3600

        jwt_info = {
            'iss': self.merchant_id,
            'aud': 'Google',
            'typ': 'google/payments/inapp/item/v1',
            'iat': current_time,
            'exp': exp_time,
            'request': {
                "currencyCode": self.payment.currency,
                "price": str(self.payment.total),
                'name': self.payment.description or u"Total payment",
                'sellerData': self.payment.token,
            }
        }

        return jwt.encode(jwt_info, self.merchant_secret)

    def get_form(self, data=None):
        return PaymentForm(data=data, payment=self.payment, provider=self, action='', hidden_inputs=False)

    def process_data(self, request):
        form = ProcessPaymentForm(payment=self.payment, provider=self,
                                  data=request.POST or None)
        if not form.is_valid():
            return HttpResponseForbidden('FAILED')
        form.save()
        return HttpResponse('OK')
