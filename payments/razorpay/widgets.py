from django.forms.widgets import HiddenInput
from django.utils.html import format_html
from django.utils.translation import ugettext_lazy as _

try:
    from django.forms.utils import flatatt
except ImportError:
    from django.forms.util import flatatt

CHECKOUT_SCRIPT_URL = 'https://checkout.razorpay.com/v1/checkout.js'


# TODO: add note to docs: you can use any valid card number
# like 4111 1111 1111 1111 with any future expiry date and CVV in the test mode
class RazorPayCheckoutWidget(HiddenInput):
    def __init__(self, provider, payment, *args, **kwargs):
        override_attrs = kwargs.get('attrs', None)
        base_attrs = kwargs['attrs'] = {
            'src': CHECKOUT_SCRIPT_URL,
            'data-key': provider.public_key,
            'data-image': provider.image,
            'data-name': provider.name,
            'data-description': payment.description or _('Total payment'),
            'data-amount': int(payment.total * 100)
        }

        if provider.prefill:
            customer_name = '%s %s' % (
                payment.billing_last_name,
                payment.billing_first_name)
            base_attrs.update({
                'data-prefill.name': customer_name,
                'data-prefill.email': payment.billing_email
            })

        if override_attrs:
            base_attrs.update(override_attrs)
        super(RazorPayCheckoutWidget, self).__init__(*args, **kwargs)

    def render(self, name, *args, **kwargs):
        attrs = kwargs.setdefault('attrs', {})
        attrs.update(self.attrs)
        return format_html('<script{0}></script>', flatatt(attrs))
