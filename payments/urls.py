"""
This module is responsible for automatic processing of provider callback
data (asynchronous transaction updates).
"""

from __future__ import annotations

from django.db.transaction import atomic
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import path
from django.urls import re_path
from django.views.decorators.csrf import csrf_exempt

from . import get_payment_model
from .core import provider_factory


@csrf_exempt
@atomic
def process_data(request, token, provider=None):
    """
    Calls process_data of an appropriate provider.

    Raises Http404 if variant does not exist.
    """
    Payment = get_payment_model()
    payment = get_object_or_404(Payment, token=token)
    if not provider:
        try:
            provider = provider_factory(payment.variant, payment)
        except ValueError as e:
            raise Http404("No such payment") from e
    return provider.process_data(payment, request)


@csrf_exempt
@atomic
def static_callback(request, variant):
    try:
        provider = provider_factory(variant)
    except ValueError as e:
        raise Http404("No such provider") from e

    token = provider.get_token_from_request(request=request, payment=None)
    if not token:
        raise Http404("Invalid response")
    return process_data(request, token, provider)


urlpatterns = [
    # A per-payment callback endpoint.
    # Providers that use a unique URL for each payment will deliver webhook
    # notifications to this view.
    path("process/<uuid:token>/", process_data, name="process_payment"),
    # A static per-provider callback endpoint.
    # Providers that use single URL for all payments will deliver webhook notifications
    # to this view. Some providers (e.g.: Stripe) need to be manually configured to
    # deliver notifications to this route.
    re_path(
        r"^process/(?P<variant>[a-z-]+)/$",
        static_callback,
        name="static_process_payment",
    ),
]
