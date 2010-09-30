from .. import BasicProvider
from ..models import Payment

class DummyProvider(BasicProvider):
    '''
    Dummy payment provider

    url:
        return URL, user will be bounced to this address after payment is
        processed
    '''

    def __init__(self, url, *args, **kwargs):
        self._url = url
        return super(DummyProvider, self).__init__(*args, **kwargs)

    def get_form(self, payment):
        from forms import DummyPaymentForm
        return DummyPaymentForm(self._variant, initial={
            'payment_id': payment.id,
            'status': payment.status,
        })

    def get_hidden_fields(self, payment):
        data = {
            'payment_id': payment.id,
        }
        return data

    def process_data(self, request, variant):
        from .views import process
        return process(request, variant)

