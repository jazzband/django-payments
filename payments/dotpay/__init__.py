from __future__ import unicode_literals
from decimal import Decimal as D
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse, HttpResponseForbidden

from .forms import ProcessPaymentForm
from .. import BasicProvider


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

    def __init__(self, *args, **kwargs):
        self.endpoint = kwargs.get(
            'endpoint', 'https://ssl.dotpay.pl/test_payment/')
        self.seller_id = kwargs.pop('seller_id')
        self.pin = kwargs.pop('pin')
        self.channel = kwargs.pop('channel', 0)
        self.lang = kwargs.pop('lang', 'pl')
        self.lock = kwargs.pop('lock', False)
        super(DotpayProvider, self).__init__(*args, **kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                'Dotpay does not support pre-authorization.')

    @property
    def _action(self):
        return self.endpoint

    def get_hidden_fields(self):
        if not self.payment.description:
            raise ValueError('Payment description is required')

        data = {
            'id': self.seller_id,
            'amount': D(str(self.payment.total)).quantize(D('0.01')),
            'control': str(self.payment.id),
            'currency': self.payment.currency,
            'description': self.payment.description,
            'lang': self.lang,
            'channel': str(self.channel),
            'ch_lock': '1' if self.lock else '0',
            'URL': self.payment.get_success_url(),
            'URLC': self.get_return_url(),
            'type': '1'
        }
        return data

    def process_data(self, request):
        form = ProcessPaymentForm(payment=self.payment, pin=self.pin,
                                  data=request.POST or None)
        if not form.is_valid():
            return HttpResponseForbidden('FAILED')
        form.save()
        return HttpResponse('OK')
