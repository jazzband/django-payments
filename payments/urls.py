'''
This module is responsible for automatic processing of provider callback
data (asynchronous transaction updates).
'''
from . import factory
from .models import Payment
from django.conf.urls.defaults import patterns, url
from django.http import Http404
from django.shortcuts import get_object_or_404


def process_data(request, variant, token):
    '''
    Calls process_data of an appropriate provider.

    Raises Http404 if variant does not exist.
    '''
    payment = get_object_or_404(Payment, token=token)
    try:
        provider = factory(payment, variant)
    except ValueError:
        raise Http404('No such payment variant')
    return provider.process_data(request)

urlpatterns = patterns('',
    url(r'^process/(?P<variant>.+)/(?P<token>[0-9a-z]{8}-[0-9a-z]{4}-'
        '[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{12})$', process_data,
        name='process_payment'),)
