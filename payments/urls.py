'''
This module is responsible for automatic processing of provider callback
data (asynchronous transaction updates).
'''
from . import factory, get_payment_model
from django.conf.urls.defaults import patterns, url
from django.http import Http404
from django.shortcuts import get_object_or_404

Payment = get_payment_model()


def process_data(request, token):
    '''
    Calls process_data of an appropriate provider.

    Raises Http404 if variant does not exist.
    '''
    payment = get_object_or_404(Payment, token=token)
    try:
        provider = factory(payment)
    except ValueError:
        raise Http404('No such payment')
    return provider.process_data(request)

urlpatterns = patterns('',
    url(r'^process/(?P<token>[0-9a-z]{8}-[0-9a-z]{4}-'
        '[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{12})$', process_data,
        name='process_payment'),)
