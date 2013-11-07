import re
from collections import namedtuple
try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import get_model

PAYMENT_VARIANTS = {
    'default': ('payments.dummy.DummyProvider', {
        'url': 'http://google.pl/'})}

if not hasattr(settings, 'PAYMENT_BASE_URL'):
    raise ImproperlyConfigured('The PAYMENT_BASE_URL setting '
                               'must not be empty.')

PurchasedItem = namedtuple('PurchasedItem',
                           'name, quantity, price, currency, sku')


class RedirectNeeded(Exception):
    pass


class BasicProvider(object):
    '''
    This class defines the provider API. It should not be instantiated
    directly. Use factory instead.
    '''
    _method = 'post'

    def _action(self):
        return self.get_return_url()
    _action = property(_action)

    def __init__(self, payment):
        self.payment = payment

    def get_hidden_fields(self):
        '''
        Converts a payment into a dict containing transaction data. Use
        get_form instead to get a form suitable for templates.

        When implementing a new payment provider, overload this method to
        transfer provider-specific data.
        '''
        raise NotImplementedError()

    def get_form(self, data=None):
        '''
        Converts *payment* into a form suitable for Django templates.
        '''
        from forms import PaymentForm
        return PaymentForm(self.get_hidden_fields(),
                           self._action, self._method)

    def process_data(self, request):
        '''
        Process callback request from a payment provider.
        '''
        raise NotImplementedError()

    def get_token_from_request(self, request):
        '''
        Return payment token from provider request.
        '''
        raise NotImplementedError()

    def get_return_url(self):
        payment_link = self.payment.get_process_url()
        return urljoin(settings.PAYMENT_BASE_URL, payment_link)


def provider_factory(variant, payment=None):
    "Return the provider instance based on variant"
    variants = getattr(settings, 'PAYMENT_VARIANTS', PAYMENT_VARIANTS)
    handler, config = variants.get(variant, (None, None))
    if not handler:
        raise ValueError('Payment variant does not exist: %s' %
                         (variant,))
    path = handler.split('.')
    if len(path) < 2:
        raise ValueError('Payment variant uses an invalid payment module: %s' %
                         (variant,))
    module_path = '.'.join(path[:-1])
    klass_name = path[-1]
    module = __import__(module_path, globals(), locals(), [klass_name])
    klass = getattr(module, klass_name)
    return klass(payment, **config)


def factory(payment):
    '''
    Takes the payment object and returns an appropriate provider instance.
    '''
    return provider_factory(payment.variant, payment)


def get_payment_model():
    "Return the Payment model that is active in this project"
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
    ('^4[0-9]{12}(?:[0-9]{3})?$', 'visa', 'VISA'),
    ('^5[1-5][0-9]{14}$', 'mastercard', 'MasterCard'),
    ('^6(?:011|5[0-9]{2})[0-9]{12}$', 'discover', 'Discover'),
    ('^3[47][0-9]{13}$', 'amex', 'American Express'),
    ('^(?:(?:2131|1800|35\d{3})\d{11})$', 'jcb', 'JCB'),
    ('^(?:3(?:0[0-5]|[68][0-9])[0-9]{11})$', 'diners', 'Diners Club')]


def get_credit_card_issuer(number):
    for regexp, card_type, name in CARD_TYPES:
        if re.match(regexp, number):
            return card_type, name
    return None, None