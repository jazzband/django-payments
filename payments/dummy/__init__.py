from __future__ import unicode_literals
try:
    # For Python 3.0 and later
    from urllib.error import URLError
    from urllib.parse import urlencode
except ImportError:
    # Fall back to Python 2's urllib2
    from urllib2 import URLError
    from urllib import urlencode
from django.http import HttpResponseRedirect

from .forms import DummyForm, Dummy3DSecureForm
from .. import BasicProvider, RedirectNeeded, PaymentError


class DummyProvider(BasicProvider):
    '''
    Dummy payment provider
    '''

    def get_form(self, data=None):
        form = DummyForm(data=data, hidden_inputs=False, provider=self,
                         payment=self.payment)
        if form.is_valid():
            new_status = form.cleaned_data['status']
            self.payment.change_status(new_status)
            new_fraud_status = form.cleaned_data['fraud_status']
            self.payment.change_fraud_status(new_fraud_status)
            if new_status == 'confirmed':
                raise RedirectNeeded(self.payment.get_success_url())
            raise RedirectNeeded(self.payment.get_failure_url())
        else:
            self.payment.change_status('input')
        return form

    def process_data(self, request):
        if self.payment.status == 'confirmed':
            return HttpResponseRedirect(self.payment.get_success_url())
        return HttpResponseRedirect(self.payment.get_failure_url())

    def capture(self, amount=None):
        self.payment.change_status('confirmed')
        return amount

    def release(self):
        return None

    def refund(self, amount=None):
        return amount or 0


class Dummy3DSecureProvider(DummyProvider):
    '''
    Dummy provider with 3D-Secure support
    '''

    def get_form(self, data=None):
        form = Dummy3DSecureForm(data=data, hidden_inputs=False, provider=self,
                                 payment=self.payment)
        if form.is_valid():
            new_status = form.cleaned_data['status']
            self.payment.change_status(new_status)
            new_fraud_status = form.cleaned_data['fraud_status']
            self.payment.change_fraud_status(new_fraud_status)
            gateway_respose = form.cleaned_data['gateway_response']
            verification_result = form.cleaned_data['verification_result']
            if gateway_respose == '3ds-disabled':
                # Standard request without 3DSecure
                pass
            elif gateway_respose == '3ds-redirect':
                # Simulate redirect to 3DS and get back to normal
                # payment processing
                process_url = self.payment.get_process_url()
                params = urlencode(
                    {'verification_result': verification_result})
                redirect_url = '%s?%s' % (process_url, params)
                raise RedirectNeeded(redirect_url)
            elif gateway_respose == 'failure':
                # Gateway raises error (HTTP 500 for example)
                raise URLError('Opps')
            elif gateway_respose == 'payment-error':
                raise PaymentError('Unsupported operation')

            if new_status == 'preauth':
                raise RedirectNeeded(self.payment.get_success_url())
            raise RedirectNeeded(self.payment.get_failure_url())

        return form

    def process_data(self, request):
        verification_result = request.GET.get('verification_result')
        if verification_result:
            self.payment.change_status(verification_result)
        if self.payment.status in ['confirmed', 'preauth']:
            return HttpResponseRedirect(self.payment.get_success_url())
        return HttpResponseRedirect(self.payment.get_failure_url())
