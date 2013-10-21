from __future__ import unicode_literals
import binascii

from Crypto.Cipher import AES
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
    _action = 'https://live.sagepay.com/gateway/service/vspform-register.vsp'

    def __init__(self, *args, **kwargs):
        self._vendor = kwargs.pop('vendor')
        self._enckey = kwargs.pop('encryption_key')
        self._action = kwargs.pop('endpoint', self._action)
        return super(SagepayProvider, self).__init__(*args, **kwargs)

    def _aes_pad(self, crypt):
        padding = ""
        padlength = 16 - (len(crypt) % 16)
        for _i in range(1, padlength + 1):
            padding += chr(padlength)
        return crypt + padding

    def aes_enc(self, data):
        aes = AES.new(self._enckey, AES.MODE_CBC, self._enckey)
        data = self._aes_pad(data.encode('utf-8'))
        enc = aes.encrypt(data)
        enc = "@" + binascii.hexlify(enc)
        return enc

    def aes_dec(self, data):
        data = data.lstrip('@').decode('utf-8')
        aes = AES.new(self._enckey, AES.MODE_CBC, self._enckey)
        dec = binascii.unhexlify(data)
        dec = aes.decrypt(dec)
        return dec

    def get_hidden_fields(self):
        self.payment.save()
        return_url = self.get_return_url()
        data = {
            'VendorTxCode': self.payment.pk,
            'Amount': "%.2f" % (self.payment.total,),
            'Currency': self.payment.currency,
            'SuccessURL': return_url,
            'FailureURL': return_url,
            'Description': "Payment #%s" % (self.payment.pk,),
            'BillingSurname': self.payment.billing_last_name,
            'BillingFirstnames': self.payment.billing_first_name,
            'BillingAddress1': self.payment.billing_address_1,
            'BillingAddress2': self.payment.billing_address_2,
            'BillingCity': self.payment.billing_city,
            'BillingPostCode': self.payment.billing_postcode,
            'BillingCountry': self.payment.billing_country_code,
            'DeliverySurname': self.payment.billing_last_name,
            'DeliveryFirstnames': self.payment.billing_first_name,
            'DeliveryAddress1': self.payment.billing_address_1,
            'DeliveryAddress2': self.payment.billing_address_2,
            'DeliveryCity': self.payment.billing_city,
            'DeliveryPostCode': self.payment.billing_postcode,
            'DeliveryCountry': self.payment.billing_country_code}
        udata = "&".join("%s=%s" % kv for kv in data.items())
        crypt = self.aes_enc(udata)
        return {'VPSProtocol': self._version, 'TxType': 'PAYMENT',
                'Vendor': self._vendor, 'Crypt': crypt}

    def process_data(self, request):
        udata = self.aes_dec(request.GET['crypt'])
        data = {}
        for kv in udata.split('&'):
            k, v = kv.split('=')
            data[k] = v
        success_url = self.payment.get_success_url()
        if self.payment.status == 'waiting':
            # If the payment is not in waiting state, we probably have a page reload.
            # We should neither throw 404 nor alter the payment again in such case.
            if data['Status'] == 'OK':
                self.payment.change_status('confirmed')
                return redirect(success_url)
            else:
                # XXX: We should recognize AUTHENTICATED and REGISTERED in the future.
                self.payment.change_status('rejected')
                return redirect(self.payment.get_failure_url())
        return redirect(success_url)
