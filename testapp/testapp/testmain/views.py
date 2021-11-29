from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.template.response import TemplateResponse

from payments import RedirectNeeded
from payments import get_payment_model
from testapp.testmain.forms import TestPaymentForm


def payment_details(request, payment_id):
    """
    Defautl view implemented from docs.
    This view is intented only for interactive testing purposes.
    """
    payment = get_object_or_404(get_payment_model(), id=payment_id)
    try:
        form = payment.get_form(data=request.POST or None)
    except RedirectNeeded as redirect_to:
        return redirect(str(redirect_to))
    return TemplateResponse(request, "payment.html", {"form": form, "payment": payment})


def payment_success(request):
    return HttpResponse("Payment succeeded.")


def payment_failure(request):
    return HttpResponse("Payment failed.")


def create_test_payment(request):
    """
    Creates a basic payment with some default parameters
    to make testing easier.

    If the payment is created successfully, the user is redirected
    to the payment details view where the get_form() method is called,
    or a redirect to the providers link is triggered.
    """
    payment = get_payment_model()
    form = TestPaymentForm(
        initial={"variant": "default", "currency": "USD", "total": 10.0},
        data=request.POST or None,
    )
    if request.method == "POST" and form.is_valid():
        p = payment.objects.create(description="Product", **form.cleaned_data)
        return redirect(f"/test/payment-details/{p.id}")
    return TemplateResponse(request, "create_payment.html", {"form": form})
