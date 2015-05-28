from __future__ import unicode_literals

import braintree
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import redirect

from .forms import BraintreePaymentForm
from .. import BasicProvider, RedirectNeeded


class BraintreeProvider(BasicProvider):

    def __init__(self, merchant_id, public_key, private_key,
                 endpoint='api.sandbox.braintreegateway.com', **kwargs):
        self.merchant_id = merchant_id
        self.public_key = public_key
        self.private_key = private_key
        certificate = (braintree.Environment.braintree_root() +
                       '/ssl/api_braintreegateway_com.ca.crt')
        environment = braintree.Environment(
            endpoint, '443', True, certificate)
        braintree.Configuration.configure(
            environment, merchant_id=self.merchant_id,
            public_key=self.public_key, private_key=self.private_key)
        super(BraintreeProvider, self).__init__(**kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                'Braintreet does not support pre-authorization.')

    def get_form(self, payment, data=None):
        kwargs = {
            'data': data,
            'payment': payment,
            'provider': self,
            'action': '',
        }
        form = BraintreePaymentForm(**kwargs)
        if form.is_valid():
            form.save()
            raise RedirectNeeded(payment.get_success_url())
        else:
            payment.change_status('input')
        return form

    def process_data(self, payment, request):
        if payment.status == 'confirmed':
            return redirect(payment.get_success_url())
        return redirect(payment.get_failure_url())
