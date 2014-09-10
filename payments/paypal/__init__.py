from __future__ import unicode_literals

import logging
import requests
from datetime import timedelta
from functools import wraps
import json
from decimal import Decimal, ROUND_HALF_UP
from requests.exceptions import HTTPError

try:
    from itertools import ifilter as filter
except ImportError:
    pass

from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.utils import timezone

from .forms import PaymentForm
from .. import (
    BasicProvider, get_credit_card_issuer, PaymentError, RedirectNeeded)

# Get an instance of a logger
logger = logging.getLogger(__name__)

CENTS = Decimal('0.01')


class UnauthorizedRequest(Exception):
    pass


def authorize(fun):
    @wraps(fun)
    def wrapper(*args, **kwargs):
        self = args[0]
        self.access_token = self.get_access_token()
        try:
            response = fun(*args, **kwargs)
        except HTTPError as e:
            if e.response.status_code == 401:
                last_auth_response = self.get_last_response(is_auth=True)
                if 'access_token' in last_auth_response:
                    del last_auth_response['access_token']
                    self.set_response_data(last_auth_response, is_auth=True)
                self.access_token = self.get_access_token()
                response = fun(*args, **kwargs)
            raise
        return response

    return wrapper


class PaypalProvider(BasicProvider):
    '''
    paypal.com payment provider
    '''
    def set_response_data(self, response, is_auth=False):
        extra_data = json.loads(self.payment.extra_data or '{}')
        if is_auth:
            extra_data['auth_response'] = response
        else:
            extra_data['response'] = response
            if 'links' in response:
                extra_data['links'] = dict(
                    (link['rel'], link) for link in response['links'])
        self.payment.extra_data = json.dumps(extra_data)

    def set_response_links(self, links):
        extra_data = json.loads(self.payment.extra_data or '{}')
        extra_data['links'] = dict((link['rel'], link) for link in links)
        self.payment.extra_data = json.dumps(extra_data)

    def set_error_data(self, error):
        extra_data = json.loads(self.payment.extra_data or '{}')
        extra_data['error'] = error
        self.payment.extra_data = json.dumps(extra_data)

    @property
    def links(self):
        extra_data = json.loads(self.payment.extra_data or '{}')
        links = extra_data.get('links', {})
        return links

    @authorize
    def post(self, *args, **kwargs):
        kwargs['headers'] = {
            'Content-Type': 'application/json',
            'Authorization': self.access_token}
        if 'data' in kwargs:
            kwargs['data'] = json.dumps(kwargs['data'])
        response = requests.post(*args, **kwargs)
        try:
            data = response.json()
        except ValueError:
            data = {}
        if 400 <= response.status_code <= 500:
            self.set_error_data(data)
            logger.debug(data)
            message = 'Paypal error'
            if response.status_code == 400:
                error_data = response.json()
                logger.warning(message, extra={
                    'response': error_data,
                    'status_code': response.status_code})
                message = error_data.get('message', message)
            else:
                logger.warning(
                    message, extra={'status_code': response.status_code})
            self.payment.change_status('error', message)
            raise PaymentError(message)
        else:
            self.set_response_data(data)
        return data

    def get_last_response(self, is_auth=False):
        extra_data = json.loads(self.payment.extra_data or '{}')
        if is_auth:
            return extra_data.get('auth_response', {})
        return extra_data.get('response', {})

    def __init__(self, *args, **kwargs):
        self.secret = kwargs.pop('secret')
        self.client_id = kwargs.pop('client_id')
        self.endpoint = kwargs.pop(
            'endpoint', 'https://api.sandbox.paypal.com')
        self.oauth2_url = self.endpoint + '/v1/oauth2/token'
        self.payments_url = self.endpoint + '/v1/payments/payment'
        self.payment_execute_url = self.payments_url + '/%(id)s/execute/'
        self.payment_refund_url = (
            self.endpoint + '/v1/payments/capture/{captureId}/refund')
        super(PaypalProvider, self).__init__(*args, **kwargs)

    def get_access_token(self):
        last_auth_response = self.get_last_response(is_auth=True)
        created = self.payment.created
        now = timezone.now()
        if ('access_token' in last_auth_response and
                'expires_in' in last_auth_response and
                (created + timedelta(
                    seconds=last_auth_response['expires_in'])) > now):
            return '%s %s' % (last_auth_response['token_type'],
                              last_auth_response['access_token'])
        else:
            headers = {'Accept': 'application/json',
                       'Accept-Language': 'en_US'}
            post = {'grant_type': 'client_credentials'}
            response = requests.post(self.oauth2_url, data=post,
                                     headers=headers,
                                     auth=(self.client_id, self.secret))
            response.raise_for_status()
            data = response.json()
            last_auth_response.update(data)
            self.set_response_data(last_auth_response, is_auth=True)
            return '%s %s' % (data['token_type'], data['access_token'])

    def get_link(self, name, data):
        try:
            links = filter(lambda url: url['rel'] == name, data['links'])
        except KeyError:
            return None
        return next(links)['href']

    def get_transactions_items(self):
        for purchased_item in self.payment.get_purchased_items():
            price = purchased_item.price.quantize(
                CENTS, rounding=ROUND_HALF_UP)
            item = {'name': purchased_item.name[:127],
                    'quantity': str(purchased_item.quantity),
                    'price': str(price),
                    'currency': purchased_item.currency,
                    'sku': purchased_item.sku}
            yield item

    def get_transactions_data(self):
        items = list(self.get_transactions_items())
        sub_total = (
            self.payment.total - self.payment.delivery - self.payment.tax)
        sub_total = sub_total.quantize(CENTS, rounding=ROUND_HALF_UP)
        total = self.payment.total.quantize(CENTS, rounding=ROUND_HALF_UP)
        tax = self.payment.tax.quantize(CENTS, rounding=ROUND_HALF_UP)
        delivery = self.payment.delivery.quantize(
            CENTS, rounding=ROUND_HALF_UP)
        data = {
            'intent': 'sale' if self._capture else 'authorize',
            'transactions': [{'amount': {
                'total': str(total),
                'currency': self.payment.currency,
                'details': {
                    'subtotal': str(sub_total),
                    'tax': str(tax),
                    'shipping': str(delivery)}},
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

    def get_form(self, data=None):
        if not self.payment.id:
            self.payment.save()
        redirect_to = self.links.get('approval_url')
        if not redirect_to:
            payment = self.create_payment()
            self.payment.transaction_id = payment['id']
            redirect_to = self.links['approval_url']
        self.payment.change_status('waiting')
        raise RedirectNeeded(redirect_to['href'])

    def process_data(self, request):
        success_url = self.payment.get_success_url()
        if not 'token' in request.GET:
            return HttpResponseForbidden('FAILED')
        payer_id = request.GET.get('PayerID')
        if not payer_id:
            if self.payment.status != 'confirmed':
                self.payment.change_status('rejected')
                return redirect(self.payment.get_failure_url())
            else:
                return redirect(success_url)
        payment = self.execute_payment(payer_id)
        related_resources = payment['transactions'][0]['related_resources'][0]
        resource_key = 'sale' if self._capture else 'authorization'
        authorization_links = related_resources[resource_key]['links']
        self.set_response_links(authorization_links)
        self.payment.attrs.payer_info = payment['payer']['payer_info']
        if self._capture:
            self.payment.captured_amount = self.payment.total
            self.payment.change_status('confirmed')
        else:
            self.payment.change_status('preauth')
        return redirect(success_url)

    def create_payment(self, extra_data=None):
        product_data = self.get_product_data(extra_data)
        payment = self.post(self.payments_url, data=product_data)
        return payment

    def execute_payment(self, payer_id):
        post = {'payer_id': payer_id}
        execute_url = self.links['execute']['href']
        return self.post(execute_url, data=post)

    def get_amount_data(self, amount=None):
        return {
            'currency': self.payment.currency,
            'total': str(amount.quantize(
                CENTS, rounding=ROUND_HALF_UP))}

    def capture(self, amount=None):
        if amount is None:
            amount = self.payment.total
        amount_data = self.get_amount_data(amount)
        capture_data = {
            'amount': amount_data,
            'is_final_capture': True
        }
        url = self.links['capture']['href']
        try:
            capture = self.post(url, data=capture_data)
        except HTTPError as e:
            try:
                error = e.response.json()
            except ValueError:
                error = {}
            if error.get('name') != 'AUTHORIZATION_ALREADY_COMPLETED':
                raise e
            capture = {'state': 'completed'}
        state = capture['state']
        if state in [
                'completed', 'partially_captured', 'partially_refunded']:
            return amount
        elif state == 'pending':
            self.payment.change_status('waiting')
        elif state == 'refunded':
            self.payment.change_status('refunded')
            raise PaymentError('Payment already refunded')

    def release(self):
        url = self.links['void']['href']
        self.post(url)

    def refund(self, amount=None):
        if amount is None:
            amount = self.payment.captured_amount
        amount_data = self.get_amount_data(amount)
        refund_data = {'amount': amount_data}
        url = self.links['refund']['href']
        self.post(url, data=refund_data)
        self.payment.change_status('refunded')
        return amount


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
