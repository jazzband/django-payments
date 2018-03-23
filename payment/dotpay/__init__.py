from __future__ import unicode_literals
from decimal import Decimal
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse, HttpResponseForbidden

from .forms import ProcessPaymentForm
from ..core import BasicProvider

CENTS = Decimal('0.01')


class DotpayProvider(BasicProvider):
    '''
    dotpay.pl payment provider

    seller_id:
        seller ID, assigned by dotpay
    pin:
        PIN
    channel:
        default payment channel (consult dotpay.pl reference guide)
    lang:
        UI language
    lock:
        whether to disable channels other than the default selected above
    '''
    _method = 'post'

    def __init__(self, seller_id, pin,
                 endpoint='https://ssl.dotpay.pl/test_payment/',
                 channel=0, lang='pl', lock=False, **kwargs):
        self.seller_id = seller_id
        self.pin = pin
        self.endpoint = endpoint
        self.channel = channel
        self.lang = lang
        self.lock = lock
        super(DotpayProvider, self).__init__(**kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                'Dotpay does not support pre-authorization.')

    def get_action(self, payment):
        return self.endpoint

    def get_hidden_fields(self, payment):
        if not payment.description:
            raise ValueError('Payment description is required')

        data = {
            'id': self.seller_id,
            'amount': Decimal(str(payment.total)).quantize(CENTS),
            'control': str(payment.id),
            'currency': payment.currency,
            'description': payment.description,
            'lang': self.lang,
            'channel': str(self.channel),
            'ch_lock': '1' if self.lock else '0',
            'URL': payment.get_success_url(),
            'URLC': self.get_return_url(payment),
            'type': '1'}
        return data

    def process_data(self, payment, request):
        form = ProcessPaymentForm(payment=payment, pin=self.pin,
                                  data=request.POST or None)
        if not form.is_valid():
            return HttpResponseForbidden('FAILED')
        form.save()
        return HttpResponse('OK')
