from __future__ import unicode_literals

from django.forms.util import flatatt
from django.forms.widgets import Input
from django.utils.html import format_html
from django.utils.encoding import force_text
from django.utils.translation import ugettext_lazy as _


class StripeWidget(Input):
    is_hidden = True

    def __init__(self, provider, payment, *args, **kwargs):
        attrs = kwargs.get('attrs', {})
        kwargs['attrs'] = {
            'class': 'stripe-button',
            'data-key': provider.public_key,
            'data-image': provider.image,
            'data-name': provider.name,
            'data-description': payment.description or _('Total payment'),
            # Stripe accepts cents
            'data-amount': int(payment.total * 100),
            'data-currency': payment.currency
        }
        kwargs['attrs'].update(attrs)
        super(StripeWidget, self).__init__(*args, **kwargs)

    def render(self, name, value, attrs=None):
        if value is None:
            value = ''
        final_attrs = self.build_attrs(
            attrs, src="https://checkout.stripe.com/checkout.js")
        del final_attrs['id']
        if value != '':
            # Only add the 'value' attribute if a value is non-empty.
            final_attrs['value'] = force_text(self._format_value(value))
        return format_html('<script{0}></script>', flatatt(final_attrs))
