from django.template.loader import render_to_string
from django.utils.translation import get_language
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from django.conf import settings
from django.contrib.sites.models import Site

from django.http import (HttpResponseBadRequest, HttpResponse,
HttpResponseRedirect, Http404, HttpResponseForbidden)

import requests
import xmltodict
import json

from .. import BasicProvider, RedirectNeeded

__version__ = '0.0.1'

PAYMENT_HOST = getattr(settings, 'PAYMENT_HOST', None)
PAYMENT_USES_SSL = getattr(settings, 'PAYMENT_USES_SSL', False)

def get_base_url():
    protocol = 'https' if PAYMENT_USES_SSL else 'http'
    if not PAYMENT_HOST:
        current_site = Site.objects.get_current()
        domain = current_site.domain
        return '%s://%s' % (protocol, domain)
    return '%s://%s' % (protocol, PAYMENT_HOST)


class SofortProvider(BasicProvider):
    
    def __init__(self, *args, **kwargs):
        self.secret = kwargs.pop('key')
        self.client_id = kwargs.pop('id')
        self.project_id = kwargs.pop('project_id')
        self.endpoint = kwargs.pop(
             'endpoint', 'https://api.sofort.com/api/xml')
        super(SofortProvider, self).__init__(*args, **kwargs)
        
    def get_form(self, data=None):
        if not self.payment.id:
            self.payment.save()
        
        base_url = get_base_url()
        xml_request = render_to_string('payments/sofort/new_transaction.xml', {
            'project_id': self.project_id,
            'language_code': get_language(),
            'interface_version': 'django-payment' + __version__,
            'amount': self.payment.total,
            'currency': self.payment.currency,
            'description': self.payment.description,
            'success_url': '%s%s' % (base_url, reverse('process_payment',kwargs={'token':self.payment.token})),
            'abort_url': '%s%s' % (base_url, reverse('process_payment',kwargs={'token':self.payment.token})),
            'customer_protection': '0',
        })
        
        response = requests.post(
            self.endpoint,
            data=xml_request.encode('utf-8'),
            headers={'Content-Type': 'application/xml; charset=UTF-8'},
            auth=(self.client_id, self.secret),
        )
        
        if response.status_code == 200:
            doc = xmltodict.parse(response.content)
            raise RedirectNeeded(doc['new_transaction']['payment_url'])


    def process_data(self, request):
        
        if not 'trans' in request.GET:
            return HttpResponseForbidden('FAILED')
        transaction_id = request.GET.get('trans')
        self.payment.transaction_id = transaction_id
        
        transaction_request = render_to_string('payments/sofort/transaction_request.xml', {'transactions': [transaction_id]})
        response = requests.post(
            self.endpoint,
            data=transaction_request.encode('utf-8'),
            headers={'Content-Type': 'application/xml; charset=UTF-8'},
            auth=(self.client_id, self.secret),
        )
        doc = xmltodict.parse(response.content)
        try:
            #If there is a transaction and status returned, the payment was successful 
            status = doc['transactions']['transaction_details']['status']
            self.payment.captured_amount = self.payment.total
            self.payment.change_status('confirmed')            
            self.payment.extra_data = json.dumps(doc)
            self.payment.billing_first_name = ' '.join(doc['transactions']['transaction_details']['sender']['holder'].split(' ')[:-1])
            self.payment.billing_last_name = doc['transactions']['transaction_details']['sender']['holder'].split(' ')[-1]
            self.payment.billing_country_code = doc['transactions']['transaction_details']['sender']['country_code']
            self.payment.save()
            success_url = self.payment.get_success_url()
            return redirect(success_url)
        except :#TypeError: 
            #Payment Failed
            self.payment.change_status('rejected')
            return redirect(self.payment.get_failure_url())