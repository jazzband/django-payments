from __future__ import unicode_literals

from django.forms.widgets import HiddenInput
from django.utils.translation import ugettext_lazy as _


class StripeWidget(HiddenInput):

    def __init__(self, provider, payment, *args, **kwargs):
        attrs = kwargs.get('attrs', {})
        kwargs['attrs'] = {
            'id': 'stripe-id',
            'data_key': provider.public_key,
            'data_description': payment.description or _('Total payment'),
            # Stripe accepts cents
            'data_amount': int(payment.total * 100),
            'data_currency': payment.currency
        }
        kwargs['attrs'].update(attrs)
        super(StripeWidget, self).__init__(*args, **kwargs)

    class Media:
        js = ['https://checkout.stripe.com/v2/checkout.js',
              'https://js.stripe.com/v2/']
