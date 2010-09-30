'''
This module is responsible for automatic processing of provider callback
data (asynchronous transaction updates).
'''

from django.conf.urls.defaults import patterns, url
from django.http import Http404
from . import factory

def process_data(request, variant):
    '''
    Calls process_data of an appropriate provider.
    
    Raises Http404 if variant does not exist.
    '''
    try:
        provider = factory(variant)
    except:
        raise Http404('No such payment variant')
    return provider.process_data(request, variant)

urlpatterns = patterns('',
    url(
        r'^process/(?P<variant>.+)/$',
        process_data,
        name='process_payment'
    ),
)

