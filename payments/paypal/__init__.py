from .. import BasicProvider, RedirectNeeded
from ..models import Payment
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.http import HttpResponseForbidden
from django.utils import simplejson
from uuid import uuid4
import requests
import urlparse

ENDPOINT = 'https://api.sandbox.paypal.com'
CLIENT_ID = 'Aap1SRAYwPfRn7kwAtF3wFIewa7CE7A8DiuIIkMORygFVlEcUwvisz9mnAo_'
SECRET = 'EGFUwhBIo0p-_GydBGntAAU4r01GTjSPbzrBsSpHrbkkNtTQDUPkweem7aXD'
OAUTH2_URL = ENDPOINT + '/v1/oauth2/token'
PAYMENTS_URL = ENDPOINT + '/v1/payments/payment'
PAYMENT_URL = PAYMENTS_URL + '/%(id)s/execute/'


class PaypalProvider(BasicProvider):
    '''
    paypal.com payment provider
    '''

    def __init__(self, *args, **kwargs):
        self._email = kwargs.pop('email')
        self._currency = kwargs.pop('currency', 'PLN')
        super(PaypalProvider, self).__init__(*args, **kwargs)
        domain = Site.objects.get_current().domain
        payment_link = reverse('process_payment',
                               kwargs={'variant': self._variant})
        self.return_url = urlparse.urlunparse(('http', domain, payment_link,
                                               None, None, None))

    def get_access_token(self):
        headers = {'Accept': 'application/json', 'Accept-Language': 'en_US'}
        post = {'grant_type': 'client_credentials'}
        response = requests.post(OAUTH2_URL, data=post, headers=headers,
                                 auth=(CLIENT_ID, SECRET))
        response.raise_for_status()
        data = response.json()
        return data['access_token']

    def get_form(self, payment):
        payment.transaction_id = str(uuid4())
        headers = {'Content-Type': 'application/json',
                   'Authorization': 'Bearer ' + self.get_access_token()}
        sub_total = payment.total - payment.delivery
        post = {
            'intent': 'sale',
            'redirect_urls': {'return_url': self.return_url,
                              'cancel_url': self.return_url},
            'payer': {'payment_method': 'paypal'},
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
        response = requests.post(PAYMENTS_URL, data=simplejson.dumps(post),
                                 headers=headers)
        response.raise_for_status()
        data = response.json()
        links = data['links']
        approval_url = filter(lambda url: url['rel'] == 'approval_url', links)
        payment.save()
        raise RedirectNeeded(approval_url[0]['href'])

    def process_data(self, request):
        try:
            token = request.GET['token']
        except KeyError:
            raise HttpResponseForbidden('FAILED')
        payer_id = request.GET.get('PayerID')
        headers = {'Content-Type': 'application/json',
                   'Authorization': 'Bearer ' + self.get_access_token()}
        post = {'payer_id': payer_id}
        response = requests.post(PAYMENT_URL%{'id':1},
                                 data=simplejson.dumps(post), headers=headers)
