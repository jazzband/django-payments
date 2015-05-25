from __future__ import unicode_literals

import hashlib
import hmac
import json
import time

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse, HttpResponseForbidden
import requests

from .. import BasicProvider


class CoinbaseProvider(BasicProvider):

    _method = 'get'
    api_url = 'https://api.%(endpoint)s/v1/buttons'
    checkout_url = 'https://%(endpoint)s/checkouts'

    def __init__(self, *args, **kwargs):
        self.endpoint = kwargs.pop(
            'endpoint', 'sandbox.coinbase.com')
        self.key = kwargs.pop('key')
        self.secret = kwargs.pop('secret')
        super(CoinbaseProvider, self).__init__(*args, **kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                'Coinbase does not support pre-authorization.')

    def get_custom_token(self):
        value = 'coinbase-%s-%s' % (self.payment.token, self.key)
        return hashlib.md5(value).hexdigest()

    def get_checkout_code(self):
        api_url = self.api_url % {'endpoint': self.endpoint}
        data = {
            'button': {
                'name': self.payment.description,
                'price_string': str(self.payment.total),
                'price_currency_iso': self.payment.currency,
                'callback_url': self.get_return_url(),
                'success_url': self.payment.get_success_url(),
                'cancel_url': self.payment.get_failure_url(),
                'custom': self.get_custom_token()}}

        nonce = int(time.time() * 1e6)
        message = str(nonce) + api_url + json.dumps(data)
        signature = hmac.new(self.secret.encode(), message.encode(),
                             hashlib.sha256).hexdigest()

        headers = {
            'ACCESS_KEY': self.key,
            'ACCESS_SIGNATURE': signature,
            'ACCESS_NONCE': nonce,
            'Accept': 'application/json'}
        response = requests.post(
            api_url, data=json.dumps(data), headers=headers)

        response.raise_for_status()
        results = response.json()
        return results['button']['code']

    @property
    def _action(self):
        checkout_url = self.checkout_url % {'endpoint': self.endpoint}
        return '%s/%s' % (checkout_url, self.get_checkout_code())

    def get_hidden_fields(self):
        return {}

    def process_data(self, request):
        try:
            results = json.loads(request.body.decode("utf-8"))
        except (ValueError, TypeError):
            return HttpResponseForbidden('FAILED')

        if results['order']['custom'] != self.get_custom_token():
            return HttpResponseForbidden('FAILED')

        if self.payment.status == 'waiting':
            self.payment.transaction_id = results['order']['transaction']['id']
            self.payment.change_status('confirmed')
            self.payment.save()
        return HttpResponse('OK')
