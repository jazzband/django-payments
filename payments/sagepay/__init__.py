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
        super().__init__(**kwargs)
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
        data = {
            'VendorTxCode': payment.pk,
            'Amount': "{:.2f}".format(payment.total),
            'Currency': payment.currency,
            'Description': "Payment #{}".format(payment.pk),
            'SuccessURL': return_url,
            'FailureURL': return_url,
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
        if payment.billing_country_code == 'US':
            data['BillingState'] = payment.billing_country_area
            data['DeliveryState'] = payment.billing_country_area
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
