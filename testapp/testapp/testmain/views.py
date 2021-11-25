# Create your views here.
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.template.response import TemplateResponse

from payments import RedirectNeeded
from payments import get_payment_model


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
    raise NotImplementedError()


def payment_failure(request):
    raise NotImplementedError()
