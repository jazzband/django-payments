from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.http import HttpResponseBadRequest
from .forms import DummyPaymentForm, DummyRedirectForm
from ..models import Payment
from django.views.generic.simple import direct_to_template

def process(request, variant):
    data = request.POST
    form = DummyRedirectForm(variant, data=data)
    if not form.is_valid():
        return HttpResponseBadRequest()
    payment_id = form.cleaned_data['payment_id']
    if not 'status' in data:
        data = None
    form = DummyPaymentForm(variant, data=data, initial={
        'payment_id': payment_id,
    })
    if form.is_valid():
        payment = get_object_or_404(Payment, id=form.cleaned_data['payment_id'])
        payment.change_status(form.cleaned_data['status'])
        return HttpResponseRedirect(payment.get_provider().url(payment))

    return direct_to_template(request, 'payments/dummy/form.html', {'form': form})

