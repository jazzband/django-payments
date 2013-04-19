from .. import BasicProvider
from django.shortcuts import redirect
from forms import DummyForm


class DummyProvider(BasicProvider):
    '''
    Dummy payment provider

    url:
        return URL, user will be bounced to this address after payment is
        processed
    '''

    def __init__(self, *args, **kwargs):
        self._url = kwargs.pop('url')
        return super(DummyProvider, self).__init__(*args, **kwargs)

    def get_form(self, data=None):
        return DummyForm(data=data, hidde_inputs=False, provider=self,
                         payment=self.payment)

    def process_data(self, request):
        return redirect(self.payment.success_url)
