from __future__ import unicode_literals
import binascii

from Crypto.Cipher import AES
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import redirect

from .. import BasicProvider


class SagepayProvider(BasicProvider):
    '''
    sagepay.com payment provider

    vendor:
        vendor name
    encryption_key:
        encryption key
    endpoint:
        gateway URL to post transaction data to
    '''
    _version = '2.23'
    _action = 'https://test.sagepay.com/Simulator/VSPFormGateway.asp'

    def __init__(self, vendor, encryption_key, endpoint=_action, **kwargs):
        self._vendor = vendor
        self._enckey = encryption_key
        self._action = endpoint
        super(SagepayProvider, self).__init__(**kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                'Sagepay does not support pre-authorization.')

    def _aes_pad(self, crypt):
        padding = ""
        padlength = 16 - (len(crypt.encode('utf-8')) % 16)
        for _i in range(1, padlength + 1):
            padding += chr(padlength)
        return crypt + padding

    def aes_enc(self, data):
        aes = AES.new(self._enckey, AES.MODE_CBC, self._enckey)
        data = self._aes_pad(data)
        enc = aes.encrypt(data)
        enc = b"@" + binascii.hexlify(enc)
        return enc

    def aes_dec(self, data):
        data = data.lstrip(b'@').decode('utf-8')
        aes = AES.new(self._enckey, AES.MODE_CBC, self._enckey)
        dec = binascii.unhexlify(data)
        dec = aes.decrypt(dec)
        return dec

    def get_hidden_fields(self, payment):
        payment.save()
        return_url = self.get_return_url(payment)
        data = {
            'VendorTxCode': payment.pk,
            'Amount': "%.2f" % (payment.total,),
            'Currency': payment.currency,
            'SuccessURL': return_url,
            'FailureURL': return_url,
            'Description': "Payment #%s" % (payment.pk,),
            'BillingSurname': payment.billing_last_name,
            'BillingFirstnames': payment.billing_first_name,
            'BillingAddress1': payment.billing_address_1,
            'BillingAddress2': payment.billing_address_2,
            'BillingCity': payment.billing_city,
            'BillingPostCode': payment.billing_postcode,
            'BillingCountry': payment.billing_country_code,
            'DeliverySurname': payment.billing_last_name,
            'DeliveryFirstnames': payment.billing_first_name,
            'DeliveryAddress1': payment.billing_address_1,
            'DeliveryAddress2': payment.billing_address_2,
            'DeliveryCity': payment.billing_city,
            'DeliveryPostCode': payment.billing_postcode,
            'DeliveryCountry': payment.billing_country_code}
        udata = "&".join("%s=%s" % kv for kv in data.items())
        crypt = self.aes_enc(udata)
        return {'VPSProtocol': self._version, 'TxType': 'PAYMENT',
                'Vendor': self._vendor, 'Crypt': crypt}

    def process_data(self, payment, request):
        udata = self.aes_dec(request.GET['crypt'])
        data = {}
        for kv in udata.split('&'):
            k, v = kv.split('=')
            data[k] = v
        success_url = payment.get_success_url()
        if payment.status == 'waiting':
            # If the payment is not in waiting state, we probably have a page reload.
            # We should neither throw 404 nor alter the payment again in such case.
            if data['Status'] == 'OK':
                payment.captured_amount = payment.total
                payment.change_status('confirmed')
                return redirect(success_url)
            else:
                # XXX: We should recognize AUTHENTICATED and REGISTERED in the future.
                payment.change_status('rejected')
                return redirect(payment.get_failure_url())
        return redirect(success_url)
