from collections import namedtuple
try:
    from django.db.models import get_model
except ImportError:
    from django.apps import apps
    get_model = apps.get_model
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import pgettext_lazy

PurchasedItem = namedtuple('PurchasedItem',
                           'name, quantity, price, currency, sku')


class PaymentStatus:
    WAITING = 'waiting'
    PREAUTH = 'preauth'
    CONFIRMED = 'confirmed'
    REJECTED = 'rejected'
    REFUNDED = 'refunded'
    ERROR = 'error'
    INPUT = 'input'

    CHOICES = [
        (WAITING, pgettext_lazy('payment status', 'Waiting for confirmation')),
        (PREAUTH, pgettext_lazy('payment status', 'Pre-authorized')),
        (CONFIRMED, pgettext_lazy('payment status', 'Confirmed')),
        (REJECTED, pgettext_lazy('payment status', 'Rejected')),
        (REFUNDED, pgettext_lazy('payment status', 'Refunded')),
        (ERROR, pgettext_lazy('payment status', 'Error')),
        (INPUT, pgettext_lazy('payment status', 'Input'))]


class FraudStatus:
    UNKNOWN = 'unknown'
    ACCEPT = 'accept'
    REJECT = 'reject'
    REVIEW = 'review'

    CHOICES = [
        (UNKNOWN, pgettext_lazy('fraud status', 'Unknown')),
        (ACCEPT, pgettext_lazy('fraud status', 'Passed')),
        (REJECT, pgettext_lazy('fraud status', 'Rejected')),
        (REVIEW, pgettext_lazy('fraud status', 'Review'))]


class RedirectNeeded(Exception):
    pass


class PaymentError(Exception):

    def __init__(self, message, code=None, gateway_message=None):
        super(PaymentError, self).__init__(message)
        self.code = code
        self.gateway_message = gateway_message


class ExternalPostNeeded(Exception):
    pass


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
