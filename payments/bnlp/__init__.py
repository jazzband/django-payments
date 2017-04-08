from __future__ import unicode_literals
import hashlib
import datetime

from codecs import encode

try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin

from django.conf import settings
from django.shortcuts import redirect

from ..forms import PaymentForm
from .. import BasicProvider, RedirectNeeded


class BNLPProvider(BasicProvider):
    def __init__(self, *args, **kwargs):
        self.store_id = kwargs.pop('store_id')
        self.shared_secret = kwargs.pop('shared_secret')
        self.currency = kwargs.pop('currency')
        self.endpoint = kwargs.pop('endpoint', 'https://test.ipg-online.com/connect/gateway/processing')
        super(BNLPProvider, self).__init__(*args, **kwargs)

    def get_hidden_fields(self):
        time = datetime.datetime.now().strftime('%Y:%m:%d-%H:%M:%S')
        chargetotal = str(self.payment.total)
        hash_string = str.encode(self.store_id + time + chargetotal + self.currency + self.shared_secret)
        hash_string = encode(hash_string, 'hex')
        hash_hex = hashlib.sha1(hash_string).hexdigest()
        data = {
            'txntype': 'sale',
            'timezone': 'GMT',
            'txndatetime': time,
            'hash': hash_hex,
            'storename': self.store_id,
            'mode': 'payonly',
            'chargetotal': chargetotal,
            'oid': str(self.payment.id),
            'currency': self.currency,
            'language': 'en',
            'responseSuccessURL': '%s' % urljoin(settings.PAYMENT_BASE_URL, self.get_return_url()),
            'responseFailURL': '%s' % urljoin(settings.PAYMENT_BASE_URL, self.get_return_url()),
        }
        return data

    def get_form(self, data=None):
        return PaymentForm(self.get_hidden_fields(),
                           self.endpoint, self._method)

    def process_data(self, request):
        if 'approval_code' in request.POST and request.POST['approval_code'].startswith('Y'):
            self.payment.change_status('confirmed')
            return redirect(self.payment.get_success_url())
        return redirect(self.payment.get_failure_url())

