from unittest import TestCase

import django

if hasattr(django, 'setup'):
    django.setup()

from . import provider_factory
from .dotpay.tests import TestDotpayProvider
from .paypal.tests import TestPaypalProvider
from .stripe.tests import TestStripeProvider
from .wallet.tests import TestGoogleWalletProvider


__all__ = ['TestDotpayProvider', 'TestGoogleWalletProvider',
           'TestPaypalProvider', 'TestStripeProvider']


class TestProviderFactory(TestCase):

    def test_provider_factory(self):
        provider_factory('default')
