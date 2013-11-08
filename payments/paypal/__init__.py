from __future__ import unicode_literals
from datetime import timedelta
from functools import wraps
import json
import requests

from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.utils import timezone

from .forms import PaymentForm
from .. import BasicProvider, RedirectNeeded, get_credit_card_issuer


class UnauthorizedRequest(Exception):
    pass


def authorize(fun):
    @wraps(fun)
    def wrapper(*args, **kwargs):
        self = args[0]
        self.access_token = self.get_access_token()
        response = fun(*args, **kwargs)
        if response.status_code == 401:
            extra_data = (json.loads(self.payment.extra_data)
                          if self.payment.extra_data else {})
            if 'access_token' in extra_data:
                del extra_data['access_token']
                self.payment.extra_data = json.dumps(extra_data)
            self.access_token = self.get_access_token()
            response = fun(*args, **kwargs)
        return response

    return wrapper


class PaypalProvider(BasicProvider):
    '''
    paypal.com payment provider
    '''
    def __init__(self, *args, **kwargs):
        self.secret = kwargs.pop('secret')
        self.client_id = kwargs.pop('client_id')
        self.endpoint = kwargs.pop('endpoint',
                                   'https://api.sandbox.paypal.com')
        self.oauth2_url = self.endpoint + '/v1/oauth2/token'
        self.payments_url = self.endpoint + '/v1/payments/payment'
        self.payment_execute_url = self.payments_url + '/%(id)s/execute/'
        super(PaypalProvider, self).__init__(*args, **kwargs)

    def get_access_token(self):
        extra_data = (json.loads(self.payment.extra_data)
                      if self.payment.extra_data else {})
        created = self.payment.created
        now = timezone.now()
        if ('access_token' in extra_data and
                'expires_in' in extra_data and
                (created + timedelta(seconds=extra_data['expires_in'])) > now):
            return '%s %s' % (extra_data['token_type'],
                              extra_data['access_token'])
        else:
            headers = {'Accept': 'application/json',
                       'Accept-Language': 'en_US'}
            post = {'grant_type': 'client_credentials'}
            response = requests.post(self.oauth2_url, data=post,
                                     headers=headers,
                                     auth=(self.client_id, self.secret))
            response.raise_for_status()
            data = response.json()
            extra_data.update(data)
            self.payment.extra_data = json.dumps(extra_data)
            return '%s %s' % (data['token_type'], data['access_token'])

    def get_link(self, name, data):
        try:
            links = filter(lambda url: url['rel'] == name, data['links'])
        except KeyError:
            return None
        return links[0]['href']

    def get_transactions_items(self):
        for purchased_item in self.payment.get_purchased_items():
            item = {'name': purchased_item.name,
                    'quantity': str(purchased_item.quantity),
                    'price': str(purchased_item.price),
                    'currency': purchased_item.currency,
                    'sku': purchased_item.sku}
            yield item

    def get_transactions_data(self):
        items = list(self.get_transactions_items())
        sub_total = self.payment.total - self.payment.delivery
        data = {
            'intent': 'sale',
            'transactions': [{
                'amount': {
                    'total': str(self.payment.total),
                    'currency': self.payment.currency,
                    'details': {
                        'subtotal': str(sub_total),
                        'tax': str(self.payment.tax),
                        'shipping': str(self.payment.delivery)}},
                'item_list': {'items': items},
                'description': self.payment.description}]}
        return data

    def get_product_data(self, extra_data=None):
        return_url = self.get_return_url()
        data = self.get_transactions_data()
        data['redirect_urls'] = {'return_url': return_url,
                                 'cancel_url': return_url}
        data['payer'] = {'payment_method': 'paypal'}
        return data

    @authorize
    def get_payment_response(self, extra_data=None):
        headers = {'Content-Type': 'application/json',
                   'Authorization': self.access_token}
        post = json.dumps(
            self.get_product_data(extra_data))
        return requests.post(self.payments_url, data=post, headers=headers)

    @authorize
    def get_payment_execute_response(self, payer_id):
        headers = {'Content-Type': 'application/json',
                   'Authorization': self.access_token}
        post = {'payer_id': payer_id}
        transaction_id = self.payment.transaction_id
        execute_url = self.payment_execute_url % {'id': transaction_id}
        return requests.post(execute_url, data=json.dumps(post),
                             headers=headers)

    def get_form(self, data=None):
        if not self.payment.id:
            self.payment.save()
        extra_data = (json.loads(self.payment.extra_data)
                      if self.payment.extra_data else {})
        redirect_to = self.get_link('approval_url', extra_data)
        if not redirect_to:
            response = self.get_payment_response()
            response.raise_for_status()
            response_data = response.json()
            redirect_to = self.get_link('approval_url', response_data)
            self.payment.transaction_id = response_data['id']
            extra_data['links'] = response_data['links']
            if extra_data:
                self.payment.extra_data = json.dumps(extra_data)
        self.payment.change_status('waiting')
        self.payment.save()
        raise RedirectNeeded(redirect_to)

    def process_data(self, request):
        extra_data = (json.loads(self.payment.extra_data)
                      if self.payment.extra_data else {})
        success_url = self.payment.get_success_url()
        if not 'token' in request.GET:
            return HttpResponseForbidden('FAILED')
        payer_id = request.GET.get('PayerID')
        if not payer_id:
            if self.payment.status != 'confirmed':
                self.payment.change_status('rejected')
                self.payment.save()
                return redirect(self.payment.get_failure_url())
            else:
                return redirect(success_url)
        response = self.get_payment_execute_response(payer_id)
        response.raise_for_status()
        extra_data['payer_id'] = payer_id
        self.payment.extra_data = json.dumps(extra_data)
        self.payment.change_status('confirmed')
        self.payment.save()
        return redirect(success_url)


class PaypalCardProvider(PaypalProvider):
    '''
    paypal.com credit card payment provider
    '''
    def get_form(self, data=None):
        if self.payment.status == 'waiting':
            self.payment.change_status('input')
        form = PaymentForm(data, provider=self, payment=self.payment)
        if form.is_valid():
            raise RedirectNeeded(self.payment.get_success_url())
        return form

    def get_product_data(self, extra_data):
        data = self.get_transactions_data()
        year = extra_data['expiration'].year
        month = extra_data['expiration'].month
        number = extra_data['number']
        card_type, _card_issuer = get_credit_card_issuer(number)
        credit_card = {'number': number,
                       'type': card_type,
                       'expire_month': month,
                       'expire_year': year}
        if 'cvv2' in extra_data and extra_data['cvv2']:
            credit_card['cvv2'] = extra_data['cvv2']
        data['payer'] = {'payment_method': 'credit_card',
                         'funding_instruments': [{'credit_card': credit_card}]}
        return data

    def process_data(self, request):
        return HttpResponseForbidden('FAILED')
