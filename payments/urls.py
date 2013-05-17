'''
This module is responsible for automatic processing of provider callback
data (asynchronous transaction updates).
'''
from django.conf.urls import patterns, url
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from . import factory, get_payment_model, provider_factory

Payment = get_payment_model()


@csrf_exempt
def process_data(request, token, provider=None):
    '''
    Calls process_data of an appropriate provider.

    Raises Http404 if variant does not exist.
    '''
    payment = get_object_or_404(Payment, token=token)
    if provider:
        provider.payment = payment
    else:
        try:
            provider = factory(payment)
        except ValueError:
            raise Http404('No such payment')
    return provider.process_data(request)


@csrf_exempt
def static_callback(request, variant):

    try:
        provider = provider_factory(variant)
    except ValueError:
        raise Http404('No such provider')

    token = provider.get_token_from_request(request)
    if not token:
        raise Http404('Invalid response')
    return process_data(request, token, provider)


urlpatterns = patterns('',
    url(r'^process/(?P<token>[0-9a-z]{8}-[0-9a-z]{4}-'
        '[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{12})$', process_data,
        name='process_payment'),
    url(r'^process/(?P<variant>[a-z-]+)$', static_callback,
        name='static_process_payment'),)
