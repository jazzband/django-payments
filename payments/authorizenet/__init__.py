from __future__ import unicode_literals

from django.http import HttpResponseForbidden
import requests

from .forms import PaymentForm
from .. import BasicProvider


class AuthorizeNetProvider(BasicProvider):

    def __init__(self, *args, **kwargs):
        self.login_id = kwargs.pop('login_id')
        self.transaction_key = kwargs.pop('transaction_key')
        self.endpoint = kwargs.pop(
            'endpoint', 'https://test.authorize.net/gateway/transact.dll')
        super(AuthorizeNetProvider, self).__init__(*args, **kwargs)

    def get_transactions_data(self):
        data = {
            'x_amount': self.payment.total,
            'x_currency_code': self.payment.currency,
            'x_description': self.payment.description,
            'x_first_name': self.payment.billing_first_name,
            'x_last_name': self.payment.billing_last_name,
            'x_address': "%s, %s" % (self.payment.billing_address_1,
                                     self.payment.billing_address_2),
            'x_city': self.payment.billing_city,
            'x_zip': self.payment.billing_postcode,
            'x_country': self.payment.billing_country_area
        }
        return data

    def get_product_data(self, extra_data=None):
        data = self.get_transactions_data()

        if extra_data:
            data.update(extra_data)

        data.update({
            'x_login': self.login_id,
            'x_tran_key': self.transaction_key,
            'x_delim_data': True,
            'x_delim_char': "|",
            'x_method': "CC",
            'x_type': "AUTH_CAPTURE"})

        return data

    def get_payment_response(self, extra_data=None):
        post = self.get_product_data(extra_data)
        return requests.post(self.endpoint, data=post)

    def get_form(self, data=None):
        return PaymentForm(data=data, payment=self.payment, provider=self,
                           action='')

    def process_data(self, request):
        return HttpResponseForbidden('FAILED')
