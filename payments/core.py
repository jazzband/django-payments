from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlencode
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

if TYPE_CHECKING:
    from django.http import HttpRequest

    from .models import BasePayment

PAYMENT_VARIANTS: dict[str, tuple[str, dict]] = {
    "default": ("payments.dummy.DummyProvider", {})
}

PAYMENT_HOST = getattr(settings, "PAYMENT_HOST", None)
if not PAYMENT_HOST:
    if "django.contrib.sites" not in settings.INSTALLED_APPS:
        raise ImproperlyConfigured(
            "The PAYMENT_HOST setting without the sites app must not be empty."
        )
    from django.contrib.sites.models import Site

PAYMENT_USES_SSL = getattr(settings, "PAYMENT_USES_SSL", not settings.DEBUG)


def get_base_url(request: HttpRequest | None = None) -> str:
    """Returns host url according to project settings.

    Protocol is chosen by checking ``PAYMENT_USES_SSL`` variable, and will fall
    back to plain text (``http``).

    If the ``PAYMENT_HOST`` setting is not specified, gets domain from Sites.

    Otherwise checks if it's callable and returns it's result. If it's not a
    callable treats it as domain.
    """
    protocol = "https" if PAYMENT_USES_SSL else "http"
    if not PAYMENT_HOST:
        try:
            current_site = Site.objects.get_current(request)
            domain = current_site.domain
        except Site.DoesNotExist:
            if request:
                domain = request.get_host()
            else:
                raise
    elif callable(PAYMENT_HOST):
        domain = PAYMENT_HOST()
    else:
        domain = PAYMENT_HOST
    return f"{protocol}://{domain}"


class BasicProvider:
    """Defined a base provider API.

    All providers backends should subclass this class.

    ``BasicProvider`` should not be instantiated directly. Use factory instead.
    """

    _method = "post"

    def get_action(self, payment):
        """The ``action`` for the HTML form element."""
        return self.get_return_url(payment)

    def __init__(self, capture=True):
        """Create a new provider instance.

        This method should not be called directly; use :func:`provider_factory`
        instead.
        """
        self._capture = capture

    def get_hidden_fields(self, payment):
        """
        Converts a payment into a dict containing transaction data

        Use get_form instead to get a form suitable for templates.

        When implementing a new payment provider, overload this method to
        transfer provider-specific data.
        """
        raise NotImplementedError

    def get_form(self, payment, data=None):
        """Converts ``payment`` into a form suitable for Django templates.

        This function may raise :class:`~.RedirectNeeded`, which indicates that
        the user should be redirected to a specific page.
        """
        from .forms import PaymentForm

        return PaymentForm(
            self.get_hidden_fields(payment), self.get_action(payment), self._method
        )

    def process_data(self, payment, request):
        """Process callback request from a payment provider.

        This method should handle checking the status of the payment, and
        update the ``payment`` instance.

        If a client is redirected here after making a payment, then this view
        should redirect them to either :meth:`Payment.get_success_url` or
        :meth:`Payment.get_failure_url`.
        """
        raise NotImplementedError

    def get_token_from_request(self, payment, request):
        """Return payment token from provider request."""
        raise NotImplementedError

    def get_return_url(
        self,
        payment,
        extra_data=None,
        request: HttpRequest | None = None,
    ):
        """Absolute URL where callbacks are delivered.

        This is the URL where payment providers will forward the user. Many
        payment providers include query params here to facilitate validation
        of the payment.

        Subclasses that redirect the user to the payment provider's page should
        pass this URL as a return/callback URL to providers. Requests to the
        return URL will be passed to the :meth:`~process_data` method.

        Subclasses do not generally need to override this method.
        """
        payment_link = payment.get_process_url()
        url = urljoin(get_base_url(request), payment_link)
        if extra_data:
            qs = urlencode(extra_data)
            return url + "?" + qs
        return url

    def capture(self, payment, amount=None):
        raise NotImplementedError

    def release(self, payment):
        raise NotImplementedError

    def refund(self, payment, amount=None):
        raise NotImplementedError


PROVIDER_CACHE = {}


def _default_provider_factory(variant: str, payment: BasePayment | None = None):
    """Return the provider instance based on ``variant``.

    :arg variant: The name of a variant defined in ``PAYMENT_VARIANTS``.
    """
    variants = getattr(settings, "PAYMENT_VARIANTS", PAYMENT_VARIANTS)
    handler, config = variants.get(variant, (None, None))
    if not handler:
        raise ValueError(f"Payment variant does not exist: {variant}")
    if variant not in PROVIDER_CACHE:
        class_ = import_string(handler)
        PROVIDER_CACHE[variant] = class_(**config)
    return PROVIDER_CACHE[variant]


PAYMENT_VARIANT_FACTORY = getattr(settings, "PAYMENT_VARIANT_FACTORY", None)
if PAYMENT_VARIANT_FACTORY:
    provider_factory = import_string(PAYMENT_VARIANT_FACTORY)
else:
    provider_factory = _default_provider_factory

CARD_TYPES = [
    (r"^4[0-9]{12}(?:[0-9]{3,6})?$", "visa", "VISA"),
    (
        r"^(?:5[1-5][0-9]{2}|222[1-9]|22[3-9][0-9]|2[3-6][0-9]{2}|27[01][0-9]|2720)[0-9]{12}$",
        "mastercard",
        "MasterCard",
    ),
    (r"^6(?:011|5[0-9]{2})[0-9]{12,15}$", "discover", "Discover"),
    (r"^3[47][0-9]{13}$", "amex", "American Express"),
    (r"^(?:(?:2131|1800|35\d{3})\d{11})$", "jcb", "JCB"),
    (r"^(?:3(?:0[0-5]|[68][0-9])[0-9]{11})$", "diners", "Diners Club"),
    (r"^(?:5[0678]\d\d|6304|6390|67\d\d)\d{8,15}$", "maestro", "Maestro"),
]


def get_credit_card_issuer(number: str) -> tuple[str | None, str | None]:
    for regexp, card_type, name in CARD_TYPES:
        if re.match(regexp, number):
            return card_type, name
    return None, None
