.. _backends:

Provider backends
=================

These are the payment provider backend implementations included in this
package. Note that you should not usually instantiate these yourself, but use
:func:`.provider_factory` instead.

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
                  'use_token': True,
                  'endpoint_secret': 'whsec_123456',
                  'secure_endpoint': True
              }
          )
      }
      # Settings for Development
      PAYMENT_VARIANTS = {
          'stripe': (
              'payments.stripe.StripeProviderV3',
              {
                  'api_key': 'sk_test_123456',
                  'use_token': True,
                  'secure_endpoint': False
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

Community Backends
------------------

These are the community providers compatible with ``django-payments``

.. list-table:: Community Backends
  :widths: 30 10 60
  :header-rows: 1

  * - Payment Backend
    - Country
    - Repo
  * - `Mollie <https://www.mollie.com/>`_
    - Worldwide
    - `fourdigits/django-payments-mollie <https://github.com/fourdigits/django-payments-mollie>`_
  * - `Redsys <https://pagosonline.redsys.es/index.html>`_
    - ES
    - `ajostergaard/django-payments-redsys <https://github.com/ajostergaard/django-payments-redsys>`_
  * - `click <https://click.uz>`_
    - UZ
    - `click-llc/click-integration-django <https://github.com/click-llc/click-integration-django>`_
  * - `BNL Positivity <http://www.bnlpositivity.it>`_
    - IT
    - `esistgut/django-payments-bnlepos <https://github.com/esistgut/django-payments-bnlepos>`_
  * - `PayU <https://payu.com>`_
    - World Wide
    - `PetrDlouhy/django-payments-payu <https://github.com/PetrDlouhy/django-payments-payu>`_
  * - `RazorPay <https://razorpay.com/>`_
    - IN
    - `NyanKiyoshi/django-payments-razorpay <https://github.com/NyanKiyoshi/django-payments-razorpay>`_
  * - `Flow Chile <https://flow.cl>`_
    - CL
    - `mariofix/django-payments-flow <https://github.com/mariofix/django-payments-flow>`_
  * - `Khipu <https://khipu.com>`_
    - CL
    - `mariofix/django-payments-khipu <https://github.com/mariofix/django-payments-khipu>`_


Creating a New Provider Backend
-------------------------------

Django Payments provides a flexible framework for integrating various payment
providers into your Django application. This guide will walk you through the
steps to create a new payment provider in Django Payments.

Create a Provider Class
"""""""""""""""""""""""

* Create a new Python module for your provider in the Django Payments project.
* Inside the module, define a class for your provider, inheriting from the base
  `BaseProvider` class provided by Django Payments.


.. code-block:: python

    from payments.providers.base import BaseProvider

    class MyPaymentProvider(BaseProvider):
      def process_data(self, payment, request):
          # Implement webhook processing logic
          pass

      def get_form(self, payment, data=None):
          # Implement payment form rendering logic
          pass

      def capture(self, payment, amount=None):
          # Implement payment capture logic
          raise NotImplementedError("Capture method not implemented.")

      def refund(self, payment, amount=None):
          # Implement payment refund logic
          raise NotImplementedError("Refund method not implemented.")

.. hint::

  Check with the integrator to see if they suppoer capture/refund

Implement the mandatory methods specific to your payment provider. Here are the
mandatory methods used by Django Payments:

* ``process_data(payment, request)``: This method is responsible for processing
  webhook calls from the payment gateway. It receives a payment object
  representing the payment being processed and the request object. Implement the
  logic to handle the webhook data received from the payment gateway and update
  the payment status or perform any necessary actions.

* ``get_form(payment, data=None)``: This method is responsible for rendering the
  payment form to be displayed within your Django application. It receives a
  payment  object representing the payment being made and an optional data
  parameter if form submission data is provided. Implement the logic to render
  the payment form, customize it based on your payment gateway requirements, and
  handle form submission.

* ``capture(payment, amount=None)``: This method is responsible for capturing the
  payment amount. It receives a payment object representing the payment to be
  captured and an optional amount parameter. Implement the logic to interact with
  your payment gateway's API and perform the necessary actions to capture the
  payment amount. If capturing is not supported by your payment gateway,
  set `capture: False.` to skip capture.

* ``refund(payment, amount=None)``: This method is responsible for refunding a
  payment. It receives a payment object representing the payment to be refunded
  and an optional amount parameter. Implement the logic to interact with your
  payment gateway's API and initiate the refund process. If refunding is not
  supported by your payment gateway, raise a NotImplementedError.

Make sure to implement these methods in your provider class and handle any
exceptions or errors that may occur during the payment processing or refunding
process.

By implementing these mandatory methods in your provider class, you can
integrate your payment gateway with Django Payments and provide the necessary
functionality to process payments, display payment forms, capture payments, and
handle refunds.
