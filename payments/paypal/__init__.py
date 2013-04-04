from .. import BasicProvider
from ..models import Payment


class PaypalProvider(BasicProvider):
    '''
    paypal.com payment provider
    '''
    _version = '2.23'
    _action = 'https://www.sandbox.paypal.com/cgi-bin/webscr'

    def __init__(self, *args, **kwargs):
        self._email = kwargs.pop('email')
        self._action = kwargs.pop('gateway', self._action)
        return super(PaypalProvider, self).__init__(*args, **kwargs)

    def get_hidden_fields(self, payment):
        data = {
            'invoice': payment.id,
            'first_name': payment.first_name,
            'last_name': payment.last_name,
            'city': payment.city,
            'state': payment.country_area,
            'zip': payment.zip,
            'country': payment.country,
            'currency_code': payment.currency,
            'amount': payment.total,
            'cmd': '_cart',
            'upload': '1',
            'charset': 'utf-8',
            'business': self._email
        }
        for index, item in enumerate(self.order_items, 1):
            data['item_name_%d' % index] = unicode(item)
            data['amount_%d' % index] = item.unit_price_gross
            data['quantity_%d' % index] = item.quantity
        return data

    def process_data(self, request, variant):
        pass
