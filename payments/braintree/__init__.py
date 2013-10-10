from django.core.urlresolvers import reverse
from django.http import HttpResponseForbidden, HttpResponse

from .. import get_payment_model, BasicProvider, RedirectNeeded
from django.shortcuts import redirect
import braintree
from .forms import BraintreePaymentForm

Payment = get_payment_model()


class BraintreeProvider(BasicProvider):

    def __init__(self, *args, **kwargs):
        self.merchant_id = kwargs.pop('merchant_id')
        self.public_key = kwargs.pop('public_key')
        self.private_key = kwargs.pop('private_key')

        braintree.Configuration.configure(braintree.Environment.Sandbox,
                                          merchant_id=self.merchant_id,
                                          public_key=self.public_key,
                                          private_key=self.private_key)

        super(BraintreeProvider, self).__init__(*args, **kwargs)

    def get_form(self, data=None):
        kwargs = {
            'data': data,
            'payment': self.payment,
            'provider': self,
            'action': '',
        }
        form = BraintreePaymentForm(**kwargs)
        if form.is_valid():
            form.save()
            raise RedirectNeeded(self.payment.get_success_url())
        else:
            self.payment.change_status('input')
        return form

    def get_process_form(self, request):
        return BraintreePaymentForm(payment=self.payment, provider=self,
                                    data=request.POST or None)

    def process_data(self, request):
        if self.payment.status == 'confirmed':
            return redirect(self.payment.get_success_url())
        return redirect(self.payment.get_failure_url())
