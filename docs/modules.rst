Provided backends
=================

These are the payment provider implementations included in this package. Note that you
should not usually instantiate these yourself, but use :func:`provider_factory`
instead.

Dummy
-----

.. autoclass:: payments.dummy.DummyProvider

Example::

      PAYMENT_VARIANTS = {
          'dummy': ('payments.dummy.DummyProvider', {})}


Authorize.Net
-------------

.. autoclass:: payments.authorizenet.AuthorizeNetProvider

Example::

      # use staging environment
      PAYMENT_VARIANTS = {
          'authorizenet': ('payments.authorizenet.AuthorizeNetProvider', {
              'login_id': '1234login',
              'transaction_key': '1234567890abcdef',
              'endpoint': 'https://test.authorize.net/gateway/transact.dll'})}

Braintree
---------

.. autoclass:: payments.braintree.BraintreeProvider

Example::

      # use sandbox
      PAYMENT_VARIANTS = {
          'braintree': ('payments.braintree.BraintreeProvider', {
              'merchant_id': '112233445566',
              'public_key': '1234567890abcdef',
              'private_key': 'abcdef123456',
              'sandbox': True})}


Coinbase
--------

.. autoclass:: payments.coinbase.CoinbaseProvider

  .. automethod:: __init__

Example::

      # use sandbox
      PAYMENT_VARIANTS = {
          'coinbase': ('payments.coinbase.CoinbaseProvider', {
              'key': '123abcd',
              'secret': 'abcd1234',
              'endpoint': 'sandbox.coinbase.com'})}


Cybersource
-----------

.. autoclass:: payments.cybersource.CyberSourceProvider

Example::

      # use sandbox
      PAYMENT_VARIANTS = {
          'cybersource': ('payments.cybersource.CyberSourceProvider', {
              'merchant_id': 'example',
              'password': '1234567890abcdef',
              'capture': False,
              'sandbox': True})}

Merchant-Defined Data
"""""""""""""""""""""

Cybersource allows you to pass Merchant-Defined Data, which is additional information
about the payment or the order, such as an order number, additional customer
information, or a special comment or request from the customer. This can be
accomplished by passing your data to the :class:`Payment` instance::

      >>> payment.attrs.merchant_defined_data = {'01': 'foo', '02': 'bar'}


Dotpay
------

.. autoclass:: payments.dotpay.DotpayProvider

Example::

      # use defaults for channel and lang but lock available channels
      PAYMENT_VARIANTS = {
          'dotpay': ('payments.dotpay.DotpayProvider', {
              'seller_id': '123',
              'pin': '0000',
              'lock': True,
              'endpoint': 'https://ssl.dotpay.pl/test_payment/'})}


Google Wallet
-------------

.. autoclass:: payments.wallet.GoogleWalletProvider

Example::

      # use sandbox
      PAYMENT_VARIANTS = {
          'wallet': ('payments.wallet.GoogleWalletProvider', {
              'seller_id': '112233445566',
              'seller_secret': '1234567890abcdef',
              'library': 'https://sandbox.google.com/checkout/inapp/lib/buy.js'})}

This backend requires js files that should be added to the template using ``{{ form.media }}`` e.g:

.. code-block:: html

      <!-- templates/payment.html -->
      <form action="{{ form.action }}" method="{{ form.method }}">
          {{ form.as_p }}
          <p><input type="submit" value="Proceed" /></p>
      </form>
      {{ form.media }}

To specify the `postback URL` at the Merchant Settings page use direct url to `process payment view` in conjunction with your `variant name`:

E.g.: ``https://example.com/payments/process/wallet``


PayPal
------

.. autoclass:: payments.paypal.PaypalProvider

Example::

      # use sandbox
      PAYMENT_VARIANTS = {
          'paypal': ('payments.paypal.PaypalProvider', {
              'client_id': 'user@example.com',
              'secret': 'iseedeadpeople',
              'endpoint': 'https://api.sandbox.paypal.com',
              'capture': False})}

.. autoclass:: payments.paypal.PaypalCardProvider

Example::

      PAYMENT_VARIANTS = {
          'paypal': ('payments.paypal.PaypalCardProvider', {
              'client_id': 'user@example.com',
              'secret': 'iseedeadpeople'})}

Sage Pay
--------

.. autoclass:: payments.sagepay.SagepayProvider

Example::

      # use simulator
      PAYMENT_VARIANTS = {
          'sage': ('payments.sagepay.SagepayProvider', {
              'vendor': 'example',
              'encryption_key': '1234567890abcdef',
              'endpoint': 'https://test.sagepay.com/Simulator/VSPFormGateway.asp'})}

Sofort / Klarna
---------------

.. autoclass:: payments.sofort.SofortProvider

Example::

      PAYMENT_VARIANTS = {
          'sage': ('payments.sofort.SofortProvider', {
              'id': '123456',
              'key': '1234567890abcdef',
              'project_id': '654321',
              'endpoint': 'https://api.sofort.com/api/xml'})}


Stripe
------

.. autoclass:: payments.stripe.StripeProvider

Example::

      # use sandbox
      PAYMENT_VARIANTS = {
          'stripe': ('payments.stripe.StripeProvider', {
              'secret_key': 'sk_test_123456',
              'public_key': 'pk_test_123456'})}

.. autoclass:: payments.stripe.StripeCardProvider
