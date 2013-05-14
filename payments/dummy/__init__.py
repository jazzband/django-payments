from django.shortcuts import redirect

from .forms import DummyForm
from .. import BasicProvider, RedirectNeeded


class DummyProvider(BasicProvider):
    '''
    Dummy payment provider

    url:
        return URL, user will be bounced to this address after payment is
        processed
    '''

    def __init__(self, *args, **kwargs):
        self._url = kwargs.pop('url')
        super(DummyProvider, self).__init__(*args, **kwargs)

    def get_form(self, data=None):
        form = DummyForm(data=data, hidden_inputs=False, provider=self,
                         payment=self.payment)
        if form.is_valid():
            new_status = form.cleaned_data['status']
            self.payment.change_status(new_status)
            if new_status == 'confirmed':
                raise RedirectNeeded(self.payment.get_success_url())
            raise RedirectNeeded(self.payment.get_failure_url())
        else:
            self.payment.change_status('input')
        return form

    def process_data(self, request):
        if self.payment.status == 'confirmed':
            return redirect(self.payment.get_success_url())
        return redirect(self.payment.get_failure_url())
