from .. import BasicProvider, RedirectNeeded
from ..models import Payment
from datetime import timedelta
from django.contrib.sites.models import Site
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.utils import simplejson, timezone
import requests
import urlparse


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

    def get_access_token(self, payment):
        extra_data = (simplejson.loads(payment.extra_data)
                      if payment.extra_data else {})
        created = payment.created
        now = timezone.now()
        if ('access_token' in extra_data and 'expires_in' in extra_data and
            (created + timedelta(seconds=extra_data['expires_in'])) > now):
            return extra_data['access_token']
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
            payment.extra_data = simplejson.dumps(extra_data)
            return data['access_token']

    def get_return_url(self, payment):
        domain = Site.objects.get_current().domain
        payment_link = payment.get_absolute_url()
        return urlparse.urlunparse(('http', domain, payment_link,
                                    None, None, None))

    def get_link(self, name, data):
        try:
            links = filter(lambda url: url['rel'] == name, data['links'])
        except KeyError:
            return None
        return links[0]['href']

    def get_transactions_data(self, payment):
        sub_total = payment.total - payment.delivery
        data = {'intent': 'sale',
                'transactions': [{
                'amount': {
                  'total': payment.total,
                  'currency': payment.currency,
                  'details': {
                        'subtotal': sub_total,
                        'tax': payment.tax,
                        'shipping': payment.delivery
                      }
                },
                'item_list': {'items': self.order_items},
                'description': payment.description}]}
        return data

    def get_product_data(self, payment):
        return_url = self.get_return_url(payment)
        data = self.get_transactions_data(payment)
        data['redirect_urls'] = {'return_url': return_url,
                                 'cancel_url': return_url},
        data['payer'] = {'payment_method': 'paypal'}
        return data

    def get_payment_data(self, payment):
        headers = {'Content-Type': 'application/json',
                   'Authorization': 'Bearer ' + self.get_access_token(payment)}
        post = self.get_product_data(payment)
        #TODO: check access_token is is vaild
        response = requests.post(self.payments_url,
                                 data=simplejson.dumps(post), headers=headers)
        response.raise_for_status()
        return response.json()

    def get_form(self, payment):
        extra_data = (simplejson.loads(payment.extra_data)
                      if payment.extra_data else {})
        redirect_to = self.get_link('approval_url', extra_data)
        if not redirect_to:
            data = self.get_payment_data(payment)
            redirect_to = self.get_link('approval_url', data)
            payment.transaction_id = data['id']
            extra_data['links'] = data['links']
            if extra_data:
                payment.extra_data = simplejson.dumps(extra_data)
        payment.status = 'redirected'
        payment.save()
        raise RedirectNeeded(redirect_to)

    def process_data(self, request, payment):
        extra_data = (simplejson.loads(payment.extra_data)
                      if payment.extra_data else {})
        try:
            _paypal_token = request.GET['token']
        except KeyError:
            raise HttpResponseForbidden('FAILED')
        payer_id = request.GET.get('PayerID')
        if not payer_id:
            payment.status = 'canceled'
            payment.save()
            return redirect(payment.cancel_url)
        headers = {'Content-Type': 'application/json',
                   'Authorization': 'Bearer ' + self.get_access_token(payment)}
        post = {'payer_id': payer_id}
        execute_url = self.payment_execute_url % {'id': payment.transaction_id}
        response = requests.post(execute_url, data=simplejson.dumps(post),
                                 headers=headers)
        response.raise_for_status()
        extra_data['payer_id'] = payer_id
        payment.extra_data = simplejson.dumps(extra_data)
        payment.status = 'success'
        payment.save()
        return redirect(payment.success_url)
