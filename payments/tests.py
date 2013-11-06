from .dotpay.tests import TestDotpayProvider
from .paypal.tests import TestPaypalProvider
from .wallet.tests import TestGoogleWalletProvider


__all__ = ['TestDotpayProvider', 'TestGoogleWalletProvider',
           'TestPaypalProvider']
