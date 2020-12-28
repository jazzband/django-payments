from decimal import Decimal

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.http import HttpResponseForbidden

from ..core import BasicProvider
from .forms import ProcessPaymentForm

CENTS = Decimal('0.01')


class DotpayProvider(BasicProvider):
    """Payment provider for dotpay.pl

    This backend implements payments using a popular Polish gateway, `Dotpay.pl
    <http://www.dotpay.pl>`_.

    Due to API limitations there is no support for transferring purchased items.

    This backend does not support fraud detection.

    :param seller_id: Seller ID assigned by Dotpay
    :param pin: PIN assigned by Dotpay
    :param channel: Default payment channel (consult reference guide). Ignored if channel_groups is set.
    :param channel_groups: Payment channels to choose from (consult reference guide). Overrides channel.
    :param lang: UI language
    :param lock: Whether to disable channels other than the default selected above
    :param endpoint: The API endpoint to use. For the production environment, use ``'https://ssl.dotpay.pl/'`` instead
    :param ignore_last_payment_channel: Display default channel or channel groups instead of last used channel.
    :param type: Determines what should be displayed after payment is completed (consult reference guide).
    """
    _method = 'post'

    def __init__(self, seller_id, pin,
                 endpoint='https://ssl.dotpay.pl/test_payment/',
                 channel=0, channel_groups=None, ignore_last_payment_channel=False,
                 lang='pl', lock=False, type=2, **kwargs):
        self.seller_id = seller_id
        self.pin = pin
        self.endpoint = endpoint
        self.channel = channel
        self.channel_groups = channel_groups
        self.ignore_last_payment_channel = ignore_last_payment_channel
        self.lang = lang
        self.lock = lock
        self.type = type
        super().__init__(**kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                'Dotpay does not support pre-authorization.')

    def get_action(self, payment):
        return self.endpoint

    def get_hidden_fields(self, payment):
        if not payment.description:
            raise ValueError('Payment description is required')

        data = {
            'id': self.seller_id,
            'amount': Decimal(str(payment.total)).quantize(CENTS),
            'control': str(payment.id),
            'currency': payment.currency,
            'description': payment.description,
            'lang': self.lang,
            'ignore_last_payment_channel':
                '1' if self.ignore_last_payment_channel else '0',
            'ch_lock': '1' if self.lock else '0',
            'URL': payment.get_success_url(),
            'URLC': self.get_return_url(payment),
            'type': str(self.type)}
        if self.channel_groups:
            data['channel_groups'] = self.channel_groups
        else:
            data['channel'] = str(self.channel)
        return data

    def process_data(self, payment, request):
        form = ProcessPaymentForm(payment=payment, pin=self.pin,
                                  data=request.POST or None)
        if not form.is_valid():
            return HttpResponseForbidden('FAILED')
        form.save()
        return HttpResponse('OK')
