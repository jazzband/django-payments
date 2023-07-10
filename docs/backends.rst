.. _backends:

Provider backends
=================

These are the payment provider backend implementations included in this
package. Note that you should not usually instantiate these yourself, but use
:func:`.provider_factory` instead.

Community Providers
-------------------

These are the community providers compatible with ``django-payments``

+--------------------------+-------------------------------------------------------------------------------------------------+------------+------------------------------------------------------------+
| Package Name             | Repo                                                                                            | Country    | Accepted Currencies                                        |
+==========================+=================================================================================================+============+============================================================+
| django-payments-mollie   | `fourdigits/django-payments-mollie <https://github.com/fourdigits/django-payments-mollie>`_       | UK         | `See List <https://docs.mollie.com/payments/multicurrency>`_|
| django-payments-redsys   | `ajostergaard/django-payments-redsys <https://github.com/ajostergaard/django-payments-redsys>`_   | ES         | EUR, USD, GBP, YEN                                         |
| click                    | `click-llc/click-integration-django <https://github.com/click-llc/click-integration-django>`_     | UZ         | See Repo                                                   |
| django-payments-bnlepos  | `esistgut/django-payments-bnlepos <https://github.com/esistgut/django-payments-bnlepos>`_         | IT         | EUR                                                        |
| django-payments-payu     | `PetrDlouhy/django-payments-payu <https://github.com/PetrDlouhy/django-payments-payu>`_           | World Wide | See Repo                                                   |
| django-payments-razorpay | `NyanKiyoshi/django-payments-razorpay <https://github.com/NyanKiyoshi/django-payments-razorpay>`_ | IN         | INR                                                        |
| django-payments-flow     | `mariofix/django-payments-flow <https://github.com/mariofix/django-payments-flow>`_               | CL         | CLP, USD                                                   |
| django-payments-khipu    | `mariofix/django-payments-khipu <https://github.com/mariofix/django-payments-khipu>`_             | CL         | CLP, USD, ARS, BOB                                         |
+--------------------------+-------------------------------------------------------------------------------------------------+------------+------------------------------------------------------------+


Integrated Providers
--------------------

Dummy
-----

.. autoclass:: payments.dummy.DummyProvider

Example::

      PAYMENT_VARIANTS = {
          'dummy': ('payments.dummy.DummyProvider', {})
      }


Authorize.Net
-------------

.. autoclass:: payments.authorizenet.AuthorizeNetProvider

Example::

      # use staging environment
      PAYMENT_VARIANTS = {
          'authorizenet': (
              'payments.authorizenet.AuthorizeNetProvider',
              {
                  'login_id': '1234login',
                  'transaction_key': '1234567890abcdef',
                  'endpoint': 'https://test.authorize.net/gateway/transact.dll'
              },
          )
      }

Braintree
---------

.. autoclass:: payments.braintree.BraintreeProvider

Example::

      # use sandbox
      PAYMENT_VARIANTS = {
          'braintree': (
              'payments.braintree.BraintreeProvider',
              {
                  'merchant_id': '112233445566',
                  'public_key': '1234567890abcdef',
                  'private_key': 'abcdef123456',
                  'sandbox': True,
              }
          )
      }


Coinbase
--------

.. autoclass:: payments.coinbase.CoinbaseProvider

  .. automethod:: __init__

Example::

      # use sandbox
      PAYMENT_VARIANTS = {
          'coinbase': (
              'payments.coinbase.CoinbaseProvider',
              {
                  'key': '123abcd',
                  'secret': 'abcd1234',
                  'endpoint': 'sandbox.coinbase.com',
              }
          )
      }

Cybersource
-----------

.. autoclass:: payments.cybersource.CyberSourceProvider

Example::

      # use sandbox
      PAYMENT_VARIANTS = {
          'cybersource': (
              'payments.cybersource.CyberSourceProvider',
              {
                  'merchant_id': 'example',
                  'password': '1234567890abcdef',
                  'capture': False,
                  'sandbox': True,
              }
          )
      }

Merchant-Defined Data
"""""""""""""""""""""

Cybersource allows you to pass Merchant-Defined Data, which is additional information
about the payment or the order, such as an order number, additional customer
information, or a special comment or request from the customer. This can be
accomplished by passing your data to the :class:`Payment` instance::

      >>> payment.attrs.merchant_defined_data = {'01': 'foo', '02': 'bar'}

Fingerprinting::

Cybersource allows you to pass a fingerprint data to help identify fraud

      >>> payment.attrs.fingerprint_session_id


Dotpay
------

.. autoclass:: payments.dotpay.DotpayProvider

Example::

      # use defaults for channel and lang but lock available channels
      PAYMENT_VARIANTS = {
          'dotpay': (
              'payments.dotpay.DotpayProvider',
              {
                  'seller_id': '123',
                  'pin': '0000',
                  'lock': True,
                  'endpoint': 'https://ssl.dotpay.pl/test_payment/',
              }
          )
      }

PayPal
------

.. autoclass:: payments.paypal.PaypalProvider

Example::

      # use sandbox
      PAYMENT_VARIANTS = {
          'paypal': (
              'payments.paypal.PaypalProvider',
              {
                  'client_id': 'user@example.com',
                  'secret': 'iseedeadpeople',
                  'endpoint': 'https://api.sandbox.paypal.com',
                  'capture': False,
              }
          )
      }

.. autoclass:: payments.paypal.PaypalCardProvider

Example::

      PAYMENT_VARIANTS = {
          'paypal': (
              'payments.paypal.PaypalCardProvider',
              {
                  'client_id': 'user@example.com',
                  'secret': 'iseedeadpeople',
              }
          )
      }

Sage Pay
--------

.. autoclass:: payments.sagepay.SagepayProvider

Example::

      # use simulator
      PAYMENT_VARIANTS = {
          'sage': (
              'payments.sagepay.SagepayProvider',
              {
                  'vendor': 'example',
                  'encryption_key': '1234567890abcdef',
                  'endpoint': 'https://test.sagepay.com/Simulator/VSPFormGateway.asp',
              }
          )
      }

Sofort / Klarna
---------------

.. autoclass:: payments.sofort.SofortProvider

Example::

      PAYMENT_VARIANTS = {
          'sage': (
              'payments.sofort.SofortProvider',
              {
                  'id': '123456',
                  'key': '1234567890abcdef',
                  'project_id': '654321',
                  'endpoint': 'https://api.sofort.com/api/xml',
              }
          )
      }


Stripe
------

.. autoclass:: payments.stripe.StripeProviderV3

Example::

      # Settings for Production
      PAYMENT_VARIANTS = {
          'stripe': (
              'payments.stripe.StripeProviderV3',
              {
                  'api_key': 'sk_test_123456',
                  'use_token': true,
                  'endpoint_secret': 'whsec_123456',
                  'secure_endpoint': true
              }
          )
      }
      # Settings for Development
      PAYMENT_VARIANTS = {
          'stripe': (
              'payments.stripe.StripeProviderV3',
              {
                  'api_key': 'sk_test_123456',
                  'use_token': true,
                  'secure_endpoint': false
              }
          )
      }

.. autoclass:: payments.stripe.StripeProvider
.. deprecated:: 2.0

Example::

      # use sandbox
      PAYMENT_VARIANTS = {
          'stripe': (
              'payments.stripe.StripeProvider',
              {
                  'secret_key': 'sk_test_123456',
                  'public_key': 'pk_test_123456',
              }
          )
      }


.. autoclass:: payments.stripe.StripeCardProvider
.. deprecated:: 2.0


MercadoPago
-----------

.. autoclass:: payments.mercadopago.MercadoPagoProvider

Example::

    PAYMENT_VARIANTS: = {
        "mercadopago": (
            "payments.mercadopago.MercadoPagoProvider",
            {
                "access_token": "APP_USR-3453454363464444-645434-7f8da79f8da7f98ad7f98ad7f98df78e-454545466",
                "sandbox": DEBUG,
            },
        ),
    }

Note that the API sandbox does not return Payment details, so all payments
will seem unpaid.
