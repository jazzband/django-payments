from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured

from .. import BasicProvider, RedirectNeeded
from .forms import PaymentForm


class StripeProvider(BasicProvider):

    def __init__(self, public_key, secret_key, image='', name='', **kwargs):
        self.secret_key = secret_key
        self.public_key = public_key
        self.image = image
        self.name = name
        super(StripeProvider, self).__init__(**kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                'Stripe does not support pre-authorization.')

    def get_form(self, payment, data=None):
        if payment.status == 'waiting':
            payment.change_status('input')
        kwargs = {
            'data': data,
            'payment': payment,
            'provider': self,
            'hidden_inputs': False}
        form = PaymentForm(**kwargs)

        if form.is_valid():
            form.save()
            raise RedirectNeeded(payment.get_success_url())
        return form
