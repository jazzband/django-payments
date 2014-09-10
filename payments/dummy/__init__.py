from __future__ import unicode_literals
from django.shortcuts import redirect

from .forms import DummyForm
from .. import BasicProvider, RedirectNeeded


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
            return redirect(self.payment.get_success_url())
        return redirect(self.payment.get_failure_url())

    def capture(self, amount=None):
        self.payment.change_status('confirmed')
        return amount

    def release(self):
        return None

    def refund(self, amount=None):
        return amount or 0
