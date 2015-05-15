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

from .. import BasicProvider, RedirectNeeded, get_base_url

__version__ = '0.0.1'

class SofortProvider(BasicProvider):
    
    def __init__(self, *args, **kwargs):
        self.secret = kwargs.pop('key')
        self.client_id = kwargs.pop('id')
        self.project_id = kwargs.pop('project_id')
        self.endpoint = kwargs.pop(
             'endpoint', 'https://api.sofort.com/api/xml')
        super(SofortProvider, self).__init__(*args, **kwargs)
    
    def post_request(self, xml_request):
        
        response = requests.post(
            self.endpoint,
            data=xml_request.encode('utf-8'),
            headers={'Content-Type': 'application/xml; charset=UTF-8'},
            auth=(self.client_id, self.secret),
        )
        doc = xmltodict.parse(response.content)
        return (doc,response,)
        
    def get_form(self, data=None):
        if not self.payment.id:
            self.payment.save()
        
        base_url = get_base_url()
        xml_request = render_to_string('payments/sofort/new_transaction.xml', {
            'project_id': self.project_id,
            'language_code': get_language(),
            'interface_version': 'django-payment-sofort' + __version__,
            'amount': self.payment.total,
            'currency': self.payment.currency,
            'description': self.payment.description,
            'success_url': '%s%s' % (base_url, reverse('process_payment',kwargs={'token':self.payment.token})),
            'abort_url': '%s%s' % (base_url, reverse('process_payment',kwargs={'token':self.payment.token})),
            'customer_protection': '0',
        })
        doc, response = self.post_request(xml_request)
        if response.status_code == 200:
            try:
                raise RedirectNeeded(doc['new_transaction']['payment_url'])
            except KeyError:
                raise Exception,'Error in %s: %s' % (doc['errors']['error']['field'],doc['errors']['error']['message'])

    def process_data(self, request):
        
        if not 'trans' in request.GET:
            return HttpResponseForbidden('FAILED')
        transaction_id = request.GET.get('trans')
        self.payment.transaction_id = transaction_id
        
        transaction_request = render_to_string('payments/sofort/transaction_request.xml', {'transactions': [transaction_id]})
        doc,response = self.post_request(transaction_request)
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
        
    def refund(self, amount=None):
        if amount is None:
            amount = self.payment.captured_amount
        sender_data = json.loads(self.payment.extra_data)['transactions']['transaction_details']['sender']
        refund_request = render_to_string('payments/sofort/refund_transaction.xml',
                                          {'holder': sender_data['holder'], #'Max Samplemerchant',#
                                           'bic': sender_data['bic'],
                                           'iban': sender_data['iban'], #'DE11888888889999999999',#
                                           'title': 'Refund Contest %s' % self.payment.contest.slug,
                                           'transaction_id': self.payment.transaction_id,
                                           'amount': amount,
                                           'comment': 'User requested a refund',
                                           })
        doc, response = self.post_request(refund_request)
        #save the response msg in "message" field
        #to start a online transaction one needs to upload the 'pain' data to his bank account
        self.payment.message = json.dumps(doc)
        self.payment.save()
        return amount
        