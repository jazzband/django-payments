from django.forms.widgets import HiddenInput
from django.utils.translation import ugettext_lazy as _


class StripeWidget(HiddenInput):

    def __init__(self, provider, payment, *args, **kwargs):
        attrs = kwargs.get('attrs', {})
        kwargs['attrs'] = {
            'id': 'stripe-id',
            'data-key': provider.public_key,
            'data-description': payment.description or _('Total payment'),
            # Stripe accepts cents
            'data-amount': payment.total * 100,
            'data-currency': payment.currency
        }
        kwargs['attrs'].update(attrs)
        super(StripeWidget, self).__init__(*args, **kwargs)

    class Media:
        js = ['https://checkout.stripe.com/v2/checkout.js',
              'js/payments/stripe.js']
