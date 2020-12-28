import time

import jwt
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.http import HttpResponseForbidden

from ..core import BasicProvider
from .forms import PaymentForm
from .forms import ProcessPaymentForm


class GoogleWalletProvider(BasicProvider):
    """Payment provider for Google Wallet.

    This backend implements payments using `Google Wallet
    <https://developers.google.com/commerce/wallet/digital/>`_ for digital goods API.

    :param seller_id: Seller ID assigned by Google Wallet
    :param seller_secret: Seller secret assigned by Google Wallet
    :param library: The API library to use. For the production environment, use ``'https://wallet.google.com/inapp/lib/buy.js'`` instead

    This backend does not support fraud detection.
    """

    def __init__(self, seller_id, seller_secret,
                 library='https://sandbox.google.com/checkout/inapp/lib/buy.js',
                 **kwargs):
        self.seller_id = seller_id
        self.seller_secret = seller_secret
        self.library = library
        super().__init__(**kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                'Google Wallet does not support pre-authorization.')

    def get_jwt_data(self, payment):

        current_time = int(time.time())
        exp_time = current_time + 3600

        jwt_info = {
            'iss': self.seller_id,
            'aud': 'Google',
            'typ': 'google/payments/inapp/item/v1',
            'iat': current_time,
            'exp': exp_time,
            'request': {
                'currencyCode': payment.currency,
                'price': str(payment.total),
                'name': payment.description or 'Total payment',
                'sellerData': payment.token}}

        return jwt.encode(jwt_info, self.seller_secret)

    def get_form(self, payment, data=None):
        kwargs = {
            'data': data,
            'payment': payment,
            'provider': self,
            'action': '',
            'hidden_inputs': False}
        return PaymentForm(**kwargs)

    def get_process_form(self, payment, request):
        return ProcessPaymentForm(payment=payment, provider=self,
                                  data=request.POST or None)

    def get_token_from_request(self, payment, request):
        form = self.get_process_form(payment, request)
        if form.is_valid():
            return form.token

    def process_data(self, payment, request):
        form = self.get_process_form(payment, request)
        if not form.is_valid():
            return HttpResponseForbidden('FAILED')
        form.save()
        return HttpResponse(form.order_id)
