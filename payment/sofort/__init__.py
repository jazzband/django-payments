import json

from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils.translation import get_language
import requests
import xmltodict

from .. import RedirectNeeded, PaymentError, PaymentStatus
from ..core import BasicProvider


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
            auth=(self.client_id, self.secret))
        doc = xmltodict.parse(response.content)
        return doc, response
        
    def get_form(self, payment, data=None):
        if not payment.id:
            payment.save()
        xml_request = render_to_string(
            'payments/sofort/new_transaction.xml', {
                'project_id': self.project_id,
                'language_code': get_language(),
                'interface_version': 'django-payments',
                'amount': payment.total,
                'currency': payment.currency,
                'description': payment.description,
                'success_url': payment.get_process_url(),
                'abort_url': payment.get_process_url(),
                'customer_protection': '0'})
        doc, response = self.post_request(xml_request)
        if response.status_code == 200:
            try:
                raise RedirectNeeded(doc['new_transaction']['payment_url'])
            except KeyError:
                raise PaymentError(
                    'Error in %s: %s' % (
                        doc['errors']['error']['field'],
                        doc['errors']['error']['message']))

    def process_data(self, payment, request):
        if not 'trans' in request.GET:
            return HttpResponseForbidden('FAILED')
        transaction_id = request.GET.get('trans')
        payment.transaction_id = transaction_id
        transaction_request = render_to_string(
            'payments/sofort/transaction_request.xml',
            {'transactions': [transaction_id]})
        doc, response = self.post_request(transaction_request)
        try:
            # If there is a transaction and status returned,
            # the payment was successful
            status = doc['transactions']['transaction_details']['status']
        except KeyError:
            # Payment Failed
            payment.change_status(PaymentStatus.REJECTED)
            return redirect(payment.get_failure_url())
        else:
            payment.captured_amount = payment.total
            payment.change_status(PaymentStatus.CONFIRMED)
            payment.extra_data = json.dumps(doc)
            sender_data = doc['transactions']['transaction_details']['sender']
            holder_data = sender_data['holder']
            first_name, last_name = holder_data.rsplit(' ', 1)
            payment.billing_first_name = first_name
            payment.billing_last_name = last_name
            payment.billing_country_code = sender_data['country_code']
            payment.save()
            return redirect(payment.get_success_url())

    def refund(self, payment, amount=None):
        if amount is None:
            amount = payment.captured_amount
        doc = json.loads(payment.extra_data)
        sender_data = doc['transactions']['transaction_details']['sender']
        refund_request = render_to_string(
            'payments/sofort/refund_transaction.xml', {
                'holder': sender_data['holder'],
                'bic': sender_data['bic'],
                'iban': sender_data['iban'],
                'title': 'Refund %s' % payment.description,
                'transaction_id': payment.transaction_id,
                'amount': amount,
                'comment': 'User requested a refund'})
        doc, response = self.post_request(refund_request)
        # save the response msg in "message" field
        # to start a online transaction one needs to upload the "pain"
        # data to his bank account
        payment.message = json.dumps(doc)
        payment.change_status(PaymentStatus.REFUNDED)
        return amount
