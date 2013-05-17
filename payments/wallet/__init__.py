import time

from django.http import HttpResponseForbidden, HttpResponse
import jwt

from .. import get_payment_model, BasicProvider
from .forms import PaymentForm, ProcessPaymentForm

Payment = get_payment_model()


class GoogleWalletProvider(BasicProvider):

    def __init__(self, *args, **kwargs):
        self.seller_id = kwargs.pop('seller_id')
        self.seller_secret = kwargs.pop('seller_secret')
        self.library = kwargs.pop('library', 'https://sandbox.google.com/checkout/inapp/lib/buy.js')
        super(GoogleWalletProvider, self).__init__(*args, **kwargs)

    def get_jwt_data(self):

        current_time = int(time.time())
        exp_time = current_time + 3600

        jwt_info = {
            'iss': self.seller_id,
            'aud': 'Google',
            'typ': 'google/payments/inapp/item/v1',
            'iat': current_time,
            'exp': exp_time,
            'request': {
                "currencyCode": self.payment.currency,
                "price": str(self.payment.total),
                'name': self.payment.description or u"Total payment",
                'sellerData': self.payment.token}}

        return jwt.encode(jwt_info, self.seller_secret)

    def get_form(self, data=None):
        return PaymentForm(data=data, payment=self.payment, provider=self, action='', hidden_inputs=False)

    def get_process_form(self, request):
        return ProcessPaymentForm(payment=self.payment, provider=self,
                                  data=request.POST or None)

    def get_token_from_request(self, request):
        form = self.get_process_form(request)
        if form.is_valid():
            return form.token

    def process_data(self, request):
        form = self.get_process_form(request)
        if not form.is_valid():
            return HttpResponseForbidden('FAILED')
        form.save()
        return HttpResponse(form.order_id)
