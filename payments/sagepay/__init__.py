import base64
import binascii
import itertools
import urlparse

from Crypto.Cipher import AES
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.template.loader import render_to_string
from django.views.generic.simple import direct_to_template

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

    def _aes_pad(self, crypt):
        padding = ""
        padlength = 16 - (len(crypt) % 16)
        for i in range(1, padlength + 1):
            padding += chr(padlength)
        return crypt + padding

    def aes_enc(self, data):
        aes = AES.new(self._enckey, AES.MODE_CBC, self._enckey)
        data = self._aes_pad(data)
        enc = aes.encrypt(data)
        enc = "@" + binascii.hexlify(enc)
        return enc

    def aes_dec(self, data):
        data = data.lstrip('@')
        aes = AES.new(self._enckey, AES.MODE_CBC, self._enckey)
        dec = binascii.unhexlify(data)
        dec = aes.decrypt(dec)
        return dec

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
            'Description': "Payment #%s" % payment.pk,
            # TODO: get real data
            'BillingSurname': 'Surname',
            'BillingFirstnames': 'Firstname Secondname',
            'BillingAddress1': 'Billing Address 1',
            'BillingCity': 'Billing City',
            'BillingPostCode': 'BLGCD1',
            'BillingCountry': 'IR',
            'DeliverySurname': 'Surname',
            'DeliveryFirstnames': 'Firstname Secondname',
            'DeliveryAddress1': 'Delivery Address 1',
            'DeliveryCity': 'Delivery City',
            'DeliveryPostCode': 'DLVCD1',
            'DeliveryCountry': 'IR'
        }
        # Parzymy Sage
        #
        # Thou shalt neither urlencode()... nor use & or = in the data of thou.
        # Otherwise - no Sage.
        udata = '&'.join("%s=%s" % kv for kv in data.items())
        crypt = self.aes_enc(udata)
        return {'VPSProtocol': self._version, 'TxType': 'PAYMENT',
                'Vendor': self._vendor, 'Crypt': crypt}

    def process_data(self, request, variant):
        udata = self.aes_dec(request.GET['crypt'])
        data = {}
        for kv in udata.split('&'):
            k, v = kv.split('=')
            data[k] = v
        payment = Payment.objects.get(pk=data['VendorTxCode'])
        if payment.status == 'waiting':
            # If the payment is not in waiting state, we probably have a page reload.
            # We should neither throw 404 nor alter the payment again in such case.
            if data['Status'] == 'OK':
                payment.change_status('confirmed')
            else:
                # XXX: We should recognize AUTHENTICATED and REGISTERED in the future.
                payment.change_status('rejected')
        return direct_to_template(request,
                'payments/sagepay/return.html',
                {'payment': payment, 'status': data['Status'], 'details': data['StatusDetail']})
