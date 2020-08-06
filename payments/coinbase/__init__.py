from collections import OrderedDict

import hashlib
import hmac
import json
import time

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse, HttpResponseForbidden
import requests

from ..core import BasicProvider
from .. import PaymentStatus


class CoinbaseProvider(BasicProvider):

    _method = 'get'
    api_url = 'https://api.%(endpoint)s/v1/buttons'
    checkout_url = 'https://%(endpoint)s/checkouts'

    def __init__(self, *args, **kwargs):
        self.endpoint = kwargs.pop(
            'endpoint', 'sandbox.coinbase.com')
        self.key = kwargs.pop('key')
        self.secret = kwargs.pop('secret')
        super().__init__(*args, **kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                'Coinbase does not support pre-authorization.')

    def get_custom_token(self, payment):
        value = 'coinbase-{}-{}'.format(payment.token, self.key)
        return hashlib.md5(value.encode('utf-8')).hexdigest()

    def get_checkout_code(self, payment):
        api_url = self.api_url % {'endpoint': self.endpoint}
        button_data = {
            'name': payment.description,
            'price_string': str(payment.total),
            'price_currency_iso': payment.currency,
            'callback_url': self.get_return_url(payment),
            'success_url': payment.get_success_url(),
            'cancel_url': payment.get_failure_url(),
            'custom': self.get_custom_token(payment)}
        # ordered dict for stable JSON output
        data = {'button': OrderedDict(sorted(button_data.items()))}
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

    def get_action(self, payment):
        checkout_url = self.checkout_url % {'endpoint': self.endpoint}
        return '{}/{}'.format(checkout_url, self.get_checkout_code(payment))

    def get_hidden_fields(self, payment):
        return {}

    def process_data(self, payment, request):
        try:
            results = json.loads(request.body)
        except (ValueError, TypeError):
            return HttpResponseForbidden('FAILED')

        if results['order']['custom'] != self.get_custom_token(payment):
            return HttpResponseForbidden('FAILED')

        if payment.status == PaymentStatus.WAITING:
            payment.transaction_id = results['order']['transaction']['id']
            payment.change_status(PaymentStatus.CONFIRMED)
            payment.save()
        return HttpResponse('OK')
