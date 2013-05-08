from django.http import HttpResponseForbidden

from ..paypal import PaypalProvider
from ..forms import PaymentForm
from .. import get_payment_model, RedirectNeeded

Payment = get_payment_model()


class PaypalCardProvider(PaypalProvider):
    '''
    paypal.com credit card payment provider
    '''
    def get_form(self, data=None):
        if self.payment.status == 'waiting':
            self.payment.change_status('input')
        form = PaymentForm(data, provider=self, payment=self.payment)
        if form.is_valid():
            raise RedirectNeeded(self.payment.get_success_url())
        return form

    def get_product_data(self, extra_data):
        data = self.get_transactions_data()
        year = extra_data['expiration'].year
        month = extra_data['expiration'].month
        credit_card = {'number': extra_data['number'],
                       'type': extra_data['type'],
                       'expire_month': month,
                       'expire_year': year}
        if 'cvv2' in extra_data and extra_data['cvv2']:
            credit_card['cvv2'] = extra_data['cvv2']
        data['payer'] = {'payment_method': 'credit_card',
                         'funding_instruments': [{'credit_card': credit_card}]}
        return data

    def process_data(self, request):
        return HttpResponseForbidden('FAILED')
