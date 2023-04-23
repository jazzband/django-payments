from django.forms.utils import flatatt
from django.forms.widgets import HiddenInput
from django.forms.widgets import Input
from django.utils.encoding import force_str
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _


class StripeCheckoutWidget(Input):
    is_hidden = True

    def __init__(self, provider, payment, *args, **kwargs):
        attrs = kwargs.get("attrs", {})
        kwargs["attrs"] = {
            "class": "stripe-button",
            "data-key": provider.public_key,
            "data-image": provider.image,
            "data-name": provider.name,
            "data-email": payment.billing_email,
            "data-description": payment.description or _("Total payment"),
            # Stripe accepts cents
            "data-amount": int(payment.total * 100),
            "data-currency": payment.currency,
        }
        kwargs["attrs"].update(attrs)
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        if value is None:
            value = ""
        final_attrs = dict(
            attrs or {}, src="https://checkout.stripe.com/checkout.js"
        )
        final_attrs.update(self.attrs)
        del final_attrs["id"]
        if value != "":
            # Only add the 'value' attribute if a value is non-empty.
            final_attrs["value"] = force_str(self.format_value(value))
        return format_html("<script{0}></script>", flatatt(final_attrs))


class StripeWidget(HiddenInput):
    class Media:
        js = ["https://js.stripe.com/v3", "js/payments/stripe.js"]

    def __init__(self, attrs=None):
        attrs = dict(attrs or {}, id="id_stripe_token")
        super().__init__(attrs)
