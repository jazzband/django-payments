from .. import BasicProvider

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

    def url(self, payment):
        if callable(self._url):
            return self._url(payment)
        return self._url

    def get_form(self, payment):
        from forms import DummyRedirectForm
        return DummyRedirectForm(self._variant, initial={
            'payment_id': payment.id,
        })

    def get_hidden_fields(self, payment):
        data = {
            'payment_id': payment.id,
        }
        return data

    def process_data(self, request, variant):
        from .views import process
        return process(request, variant)

