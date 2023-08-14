import requests
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseForbidden

from .. import PaymentStatus
from .. import RedirectNeeded
from ..core import BasicProvider
from .forms import PaymentForm


class AuthorizeNetProvider(BasicProvider):
    """Payment provider for Authorize.Net.

    This backend implements payments using the Advanced Integration Method (AIM) from
    `Authorize.Net <https://www.authorize.net/>`_.

    This backend does not support fraud detection.

    :param login_id: Your API Login ID assigned by Authorize.net
    :param transaction_key: Your unique Transaction Key assigned by Authorize.net
    :param endpoint: The API endpoint to use. For the production environment, use
        ``'https://secure.authorize.net/gateway/transact.dll'`` instead.
    """

    def __init__(
        self,
        login_id,
        transaction_key,
        endpoint="https://test.authorize.net/gateway/transact.dll",
        **kwargs,
    ):
        self.login_id = login_id
        self.transaction_key = transaction_key
        self.endpoint = endpoint
        super().__init__(**kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                "Authorize.Net does not support pre-authorization."
            )

    def get_transactions_data(self, payment):
        return {
            "x_amount": payment.total,
            "x_currency_code": payment.currency,
            "x_description": payment.description,
            "x_first_name": payment.billing_first_name,
            "x_last_name": payment.billing_last_name,
            "x_address": f"{payment.billing_address_1}, {payment.billing_address_2}",
            "x_city": payment.billing_city,
            "x_zip": payment.billing_postcode,
            "x_country": payment.billing_country_area,
            "x_customer_ip": payment.customer_ip_address,
        }

    def get_product_data(self, payment, extra_data=None):
        data = self.get_transactions_data(payment)

        if extra_data:
            data.update(extra_data)

        data.update(
            {
                "x_login": self.login_id,
                "x_tran_key": self.transaction_key,
                "x_delim_data": True,
                "x_delim_char": "|",
                "x_method": "CC",
                "x_type": "AUTH_CAPTURE",
            }
        )

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
        return HttpResponseForbidden("FAILED")
