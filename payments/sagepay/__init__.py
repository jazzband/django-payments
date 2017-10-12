from __future__ import unicode_literals
import binascii

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import redirect

from ..core import BasicProvider
from .. import PaymentStatus


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
    _version = '3.00'
    _action = 'https://test.sagepay.com/Simulator/VSPFormGateway.asp'

    def __init__(self, vendor, encryption_key, endpoint=_action, **kwargs):
        self._vendor = vendor
        self._enckey = encryption_key.encode('utf-8')
        self._action = endpoint
        super(SagepayProvider, self).__init__(**kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                'Sagepay does not support pre-authorization.')

    def _get_cipher(self):
        backend = default_backend()
        return Cipher(algorithms.AES(self._enckey), modes.CBC(self._enckey),
                      backend=backend)

    def _get_padding(self):
        return padding.PKCS7(128)

    def aes_enc(self, data):
        data = data.encode('utf-8')
        padder = self._get_padding().padder()
        data = padder.update(data) + padder.finalize()
        encryptor = self._get_cipher().encryptor()
        enc = encryptor.update(data) + encryptor.finalize()
        return b"@" + binascii.hexlify(enc)

    def aes_dec(self, data):
        data = data.lstrip(b'@')
        data = binascii.unhexlify(data)
        decryptor = self._get_cipher().decryptor()
        data = decryptor.update(data) + decryptor.finalize()
        return data.decode('utf-8')

    def get_hidden_fields(self, payment):
        payment.save()
        return_url = self.get_return_url(payment)
        _billing_address = payment.get_billing_address()
        _shipping_address = payment.get_billing_address()
        data = {
            'VendorTxCode': payment.pk,
            'Amount': "%.2f" % (payment.total,),
            'Currency': payment.currency,
            'Description': "Payment #%s" % (payment.pk,),
            'SuccessURL': return_url,
            'FailureURL': return_url,
            'BillingSurname': _billing_address["last_name"],
            'BillingFirstnames': _billing_address["first_name"],
            'BillingAddress1': _billing_address["address_1"],
            'BillingAddress2': _billing_address["address_2"],
            'BillingCity': _billing_address["city"],
            'BillingPostCode': _billing_address["postcode"],
            'BillingCountry': _billing_address["country_code"],
            'DeliverySurname': _shipping_address["last_name"],
            'DeliveryFirstnames': _shipping_address["first_name"],
            'DeliveryAddress1': _shipping_address["address_1"],
            'DeliveryAddress2': _shipping_address["address_2"],
            'DeliveryCity': _shipping_address["city"],
            'DeliveryPostCode': _shipping_address["postcode"],
            'DeliveryCountry': _shipping_address["country_code"]}
        if _billing_address["country_code"] == 'US':
            data['BillingState'] = _billing_address["country_area"]
        if _shipping_address["country_code"] == 'US':
            data['DeliveryState'] = _shipping_address["country_area"]
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
        if payment.status == PaymentStatus.WAITING:
            # If the payment is not in waiting state, we probably have a page reload.
            # We should neither throw 404 nor alter the payment again in such case.
            if data['Status'] == 'OK':
                payment.captured_amount = payment.total
                payment.change_status(PaymentStatus.CONFIRMED)
                return redirect(success_url)
            else:
                # XXX: We should recognize AUTHENTICATED and REGISTERED in the future.
                payment.change_status(PaymentStatus.REJECTED)
                return redirect(payment.get_failure_url())
        return redirect(success_url)
