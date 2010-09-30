# -*- coding: utf-8 -*-
import urlparse

from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.utils.http import urlquote
from django.http import HttpResponse, HttpResponseForbidden

from .. import BasicProvider
from ..models import Payment

from .forms import ProcessPaymentForm

class DotpayProvider(BasicProvider):
    '''
    dotpay.pl payment provider

    seller_id:
        seller ID, assigned by dotpay
    url:
        return URL, user will be bounced to this address after payment is
        processed
    pin:
        PIN
    channel:
        default payment channel (consult dotpay.pl reference guide)
    lang:
        UI language
    lock:
        whether to disable channels other than the default selected above
    '''
    _method = 'post'
    _action = 'https://ssl.dotpay.pl/'

    def __init__(self, seller_id, url, domain=None, pin=None, channel=0, lang='pl', lock=False, **kwargs):
        self._seller_id = seller_id
        self._url = url
        self._domain = domain \
                or urlparse.urlunparse((
                    'https',
                    Site.objects.get_current().domain,
                    '/',
                    None,
                    None,
                    None))
        self._pin = pin
        self._channel = channel
        self._lang = lang
        self._lock = lock
        return super(DotpayProvider, self).__init__(**kwargs)

    def get_hidden_fields(self, payment):
        get_label = lambda x: x.name if x.quantity == 1 else u'%s × %d' % (x.name, x.quantity)
        items = map(get_label, payment.items.all())

        domain = urlparse.urlparse(self._domain)
        path =  reverse('process_payment', args=[self._variant])
        urlc = urlparse.urlunparse((domain.scheme, domain.netloc, path, None, None, None))
        url_parts = urlparse.urlparse(self._url)
        if url_parts.scheme:
            url = self._url
        else:
            url = urlparse.urlunparse((domain.scheme, domain.netloc, url_parts.path, None, None, None))

        data = {
            'id': self._seller_id,
            'amount': str(payment.total),
            'control': str(payment.id),
            'currency': payment.currency,
            'description': ', '.join(items),
            'lang': self._lang,
            'channel': str(self._channel),
            'ch_lock': '1' if self._lock else '0',
            'URL': url,
            'URLC': urlc,
            'type': '2',
            'control': payment.id,
        }
        return data

    def process_data(self, request, variant):
        from django.core.mail import mail_admins
        mail_admins('Payment', unicode(request.POST) + '\n' + unicode(request.GET))
        failed = HttpResponseForbidden("FAILED")
        if request.method != "POST":
            return failed

        form = ProcessPaymentForm(pin=self._pin, data=request.POST)
        if not form.is_valid():
            return failed

        form.save()
        return HttpResponse("OK")
