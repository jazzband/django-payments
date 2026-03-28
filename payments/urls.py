"""
This module is responsible for automatic processing of provider callback
data (asynchronous transaction updates).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.transaction import atomic
from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.urls import re_path
from django.views.decorators.csrf import csrf_exempt

from . import PaymentError
from . import get_payment_model
from .core import provider_factory

if TYPE_CHECKING:
    from .core import BasicProvider


@csrf_exempt
@atomic
def process_data(
    request: HttpRequest,
    token: str,
    provider: BasicProvider | None = None,
) -> HttpResponse:
    """
    Calls process_data of an appropriate provider.

    Raises Http404 if variant does not exist.
    Note: When called via static_callback, Http404 exceptions are caught
    and converted to JSON error responses for webhook systems.
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
def static_callback(request: HttpRequest, variant: str) -> HttpResponse:
    """
    Handle webhooks sent to a static provider endpoint.

    Returns JSON responses for known error cases to provide machine-readable
    feedback to webhook systems (e.g., Stripe, PayPal).

    Unexpected exceptions will propagate and result in 500 errors, which
    will be logged by standard Django error handling and reported to Sentry.
    """
    try:
        provider = provider_factory(variant)
    except ValueError:
        return JsonResponse(
            {"error": "Invalid payment provider", "variant": variant}, status=400
        )

    try:
        token = provider.get_token_from_request(request=request, payment=None)
    except PaymentError as e:
        return JsonResponse(
            {"error": str(e), "variant": variant, "error_code": e.code},
            status=e.code or 400,
        )

    if not token:
        return JsonResponse(
            {
                "error": "Could not extract payment token from webhook",
                "variant": variant,
            },
            status=400,
        )

    try:
        return process_data(request, token, provider)
    except Http404:
        # Don't expose full token in error response for security
        return JsonResponse(
            {"error": "Payment not found", "variant": variant},
            status=404,
        )


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
