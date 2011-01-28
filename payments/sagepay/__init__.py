import base64
import itertools
import urllib
import urlparse

from Crypto.Cipher import AES
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse

from .. import BasicProvider
from ..models import Payment

class SagepayProvider(BasicProvider):
    '''
    sagepay.com payment provider

    vendor:
        vendor name
    version:
        VPSProtocol version
    gateway:
        gateway URL to post transaction data to
    '''
    _version = '2.23'
    _action = 'https://live.sagepay.com/gateway/service/vspform-register.vsp'

    def __init__(self, *args, **kwargs):
        self._vendor = kwargs.pop('vendor')
        self._enckey = kwargs.pop('encryption_key')
        self._version = kwargs.pop('version', self._version)
        self._action = kwargs.pop('gateway', self._action)
        return super(SagepayProvider, self).__init__(*args, **kwargs)

    def get_hidden_fields(self, payment):
        return_url = urlparse.urlunparse((
                'https', Site.objects.get_current().domain,
                reverse('process_payment', kwargs={'variant': payment.variant}),
                None, None, None))
        data = {
            'VendorTxCode': payment.pk,
            'Amount': "%.2f" % payment.total,
            'Currency': payment.currency,
            'SuccessURL': return_url,
            'FailureURL': return_url,
            'Description': '',
            'BillingSurname': '',
            'BillingFirstnames': '',
            'BillingAddress1': '',
            'BillingCity': '',
            'BillingPostCode': '',
            'BillingCountry': '',
            'DeliverySurname': '',
            'DeliveryFirstnames': '',
            'DeliveryAddress1': '',
            'DeliveryCity': '',
            'DeliveryPostCode': '',
            'DeliveryCountry': ''
        }
        udata = urllib.urlencode(data)
        # Although the docs say we should use AES/CBC/PKCS#5/OMG/WTF, this is just a lie.
        # We still should rely on the old, good, unbreakable... XOR.
        # TODO: Suggest SagePay developers switching to ROT13.
        #
        # PKCS#5 padding
        #pdata = udata + (32 - len(udata) % 32) * chr(5)
        #aes = AES.new(self._enckey)
        #encdata = aes.encrypt(pdata)
        #
        # Here goes the XOR:
        ebits = []
        kod = itertools.cycle(self._enckey)
        for c in udata:
            ebits.append(chr(ord(c) ^ ord(kod.next())))
        encdata = ''.join(ebits)
        # Hackishy hack goes on: remove newlines, otherwise you will get no Sage.
        crypt = base64.encodestring(encdata).replace("\n", "")
        # zaparz Sage!
        return {'VPSProtocol': self._version, 'TxType': 'PAYMENT',
                'Vendor': self._vendor, 'Crypt': crypt}

    def process_data(self, request, variant):
        pass
