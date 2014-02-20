from __future__ import unicode_literals

from django.shortcuts import redirect

from .. import BasicProvider, RedirectNeeded
from .forms import PaymentForm


class StripeProvider(BasicProvider):

    def __init__(self, *args, **kwargs):
        self.secret_key = kwargs.pop('secret_key')
        self.public_key = kwargs.pop('public_key')
        super(StripeProvider, self).__init__(*args, **kwargs)

    def get_form(self, data=None):
        kwargs = {
            'data': data,
            'payment': self.payment,
            'provider': self,
            'action': '',
            'hidden_inputs': False}
        form = PaymentForm(**kwargs)

        if form.is_valid():
            form.save()
            raise RedirectNeeded(self.payment.get_success_url())
        else:
            self.payment.change_status('input')
        return form

    def process_data(self, request):
        if self.payment.status == 'confirmed':
            return redirect(self.payment.get_success_url())
        return redirect(self.payment.get_failure_url())
