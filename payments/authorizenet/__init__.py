from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseForbidden
import requests

from .forms import PaymentForm
from .. import PaymentStatus, RedirectNeeded
from ..core import BasicProvider


class AuthorizeNetProvider(BasicProvider):

    def __init__(self, login_id, transaction_key,
                 endpoint='https://test.authorize.net/gateway/transact.dll',
                 **kwargs):
        self.login_id = login_id
        self.transaction_key = transaction_key
        self.endpoint = endpoint
        super(AuthorizeNetProvider, self).__init__(**kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                'Authorize.Net does not support pre-authorization.')

    def get_transactions_data(self, payment):
        billing = payment.get_billing_address()
        return {
            'x_amount': payment.total,
            'x_currency_code': payment.currency,
            'x_description': payment.description,
            'x_first_name': billing["first_name"],
            'x_last_name': billing["last_name"],
            'x_address': "%s, %s" % (billing["address_1"],
                                     billing["address_2"]),
            'x_city': billing["city"],
            'x_zip': billing["postcode"],
            'x_country': billing["country_area"]
        }

    def get_product_data(self, payment, extra_data=None):
        data = self.get_transactions_data(payment)

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

    def get_payment_response(self, payment, extra_data=None):
        post = self.get_product_data(payment, extra_data)
        return requests.post(self.endpoint, data=post)

    def get_form(self, payment, data=None):
        if payment.status == PaymentStatus.WAITING:
            payment.change_status(PaymentStatus.INPUT)
        form = PaymentForm(data=data, payment=payment, provider=self)
        if form.is_valid():
            raise RedirectNeeded(payment.get_success_url())
        return form

    def process_data(self, payment, request):
        return HttpResponseForbidden('FAILED')
