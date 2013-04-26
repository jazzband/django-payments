from .. import BasicProvider, RedirectNeeded
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
        if self.payment.status == 'waiting':
            self.payment.change_status('input')
        form = DummyForm(data=data, hidden_inputs=False, provider=self,
                         payment=self.payment)
        if form.is_valid():
            self.payment.change_status('confirmed')
            raise RedirectNeeded(self.payment.get_success_url())
        return form

    def process_data(self, request):
        return redirect(self.payment.get_success_url())
