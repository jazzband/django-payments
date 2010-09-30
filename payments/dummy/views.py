from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from .forms import DummyPaymentForm
from ..models import Payment
from django.views.generic.simple import direct_to_template

def process(request, variant):
    if request.method == 'POST':
        form = DummyPaymentForm(variant, request.POST)
        if form.is_valid():
            payment = get_object_or_404(Payment, id=form.cleaned_data['payment_id'])
            payment.change_status(form.cleaned_data['status'])
            return HttpResponseRedirect(str(payment.get_provider()._url))
    else:
        return HttpResponseForbidden('Only POST is supported')
    return direct_to_template(request, 'payments/dummy/form.html', {'form': form})

