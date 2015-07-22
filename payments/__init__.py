from __future__ import unicode_literals
from collections import namedtuple
import re
try:
    from urllib.parse import urljoin, urlencode
except ImportError:
    from urllib import urlencode
    from urlparse import urljoin

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.exceptions import ImproperlyConfigured
from django.db.models import get_model

PAYMENT_VARIANTS = {
    'default': ('payments.dummy.DummyProvider', {})}

PAYMENT_HOST = getattr(settings, 'PAYMENT_HOST', None)
PAYMENT_USES_SSL = getattr(settings, 'PAYMENT_USES_SSL', False)

if not PAYMENT_HOST:
    if not 'django.contrib.sites' in settings.INSTALLED_APPS:
        raise ImproperlyConfigured('The PAYMENT_HOST setting without '
                                   'the sites app must not be empty.')

PurchasedItem = namedtuple('PurchasedItem',
                           'name, quantity, price, currency, sku')


def get_base_url():
    protocol = 'https' if PAYMENT_USES_SSL else 'http'
    if not PAYMENT_HOST:
        current_site = Site.objects.get_current()
        domain = current_site.domain
        return '%s://%s' % (protocol, domain)
    return '%s://%s' % (protocol, PAYMENT_HOST)


class RedirectNeeded(Exception):
    pass


class PaymentError(Exception):
    pass


class ExternalPostNeeded(Exception):
    pass


class BasicProvider(object):
    '''
    This class defines the provider API. It should not be instantiated
    directly. Use factory instead.
    '''
    _method = 'post'

    def get_action(self, payment):
        return self.get_return_url(payment)

    def __init__(self, capture=True):
        self._capture = capture

    def get_hidden_fields(self, payment):
        '''
        Converts a payment into a dict containing transaction data. Use
        get_form instead to get a form suitable for templates.

        When implementing a new payment provider, overload this method to
        transfer provider-specific data.
        '''
        raise NotImplementedError()

    def get_form(self, payment, data=None):
        '''
        Converts *payment* into a form suitable for Django templates.
        '''
        from .forms import PaymentForm
        return PaymentForm(self.get_hidden_fields(payment),
                           self.get_action(payment), self._method)

    def process_data(self, payment, request):
        '''
        Process callback request from a payment provider.
        '''
        raise NotImplementedError()

    def get_token_from_request(self, payment, request):
        '''
        Return payment token from provider request.
        '''
        raise NotImplementedError()

    def get_return_url(self, payment, extra_data=None):
        payment_link = payment.get_process_url()
        url = urljoin(get_base_url(), payment_link)
        if extra_data:
            qs = urlencode(extra_data)
            return url + '?' + qs
        return url

    def capture(self, payment, amount=None):
        raise NotImplementedError()

    def release(self, payment):
        raise NotImplementedError()

    def refund(self, payment, amount=None):
        raise NotImplementedError()


PROVIDER_CACHE = {}


def provider_factory(variant):
    '''
    Return the provider instance based on variant
    '''
    variants = getattr(settings, 'PAYMENT_VARIANTS', PAYMENT_VARIANTS)
    handler, config = variants.get(variant, (None, None))
    if not handler:
        raise ValueError('Payment variant does not exist: %s' %
                         (variant,))
    if variant not in PROVIDER_CACHE:
        module_path, class_name = handler.rsplit('.', 1)
        module = __import__(
            str(module_path), globals(), locals(), [str(class_name)])
        class_ = getattr(module, class_name)
        PROVIDER_CACHE[variant] = class_(**config)
    return PROVIDER_CACHE[variant]


def get_payment_model():
    '''
    Return the Payment model that is active in this project
    '''
    try:
        app_label, model_name = settings.PAYMENT_MODEL.split('.')
    except (ValueError, AttributeError):
        raise ImproperlyConfigured('PAYMENT_MODEL must be of the form '
                                   '"app_label.model_name"')
    payment_model = get_model(app_label, model_name)
    if payment_model is None:
        msg = (
            'PAYMENT_MODEL refers to model "%s" that has not been installed' %
            settings.PAYMENT_MODEL)
        raise ImproperlyConfigured(msg)
    return payment_model


CARD_TYPES = [
    (r'^4[0-9]{12}(?:[0-9]{3})?$', 'visa', 'VISA'),
    (r'^5[1-5][0-9]{14}$', 'mastercard', 'MasterCard'),
    (r'^6(?:011|5[0-9]{2})[0-9]{12}$', 'discover', 'Discover'),
    (r'^3[47][0-9]{13}$', 'amex', 'American Express'),
    (r'^(?:(?:2131|1800|35\d{3})\d{11})$', 'jcb', 'JCB'),
    (r'^(?:3(?:0[0-5]|[68][0-9])[0-9]{11})$', 'diners', 'Diners Club'),
    (r'^(?:5[0678]\d\d|6304|6390|67\d\d)\d{8,15}$', 'maestro', 'Maestro')]


def get_credit_card_issuer(number):
    for regexp, card_type, name in CARD_TYPES:
        if re.match(regexp, number):
            return card_type, name
    return None, None
