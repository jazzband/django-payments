Provided backends
=================


Dummy
-----

.. class:: payments.dummy.DummyProvider

   This is a dummy backend suitable for testing your store without contacting any payment gateways. Instead of using an external service it will simply show you a form that allows you to confirm or reject the payment.

Example::

   PAYMENT_VARIANTS = {
       'dummy': ('payments.dummy.DummyProvider', {})}


Authorize.Net
-------------

.. class:: payments.authorizenet.AuthorizeNetProvider(login_id, transaction_key[, endpoint='https://secure.authorize.net/gateway/transact.dll'])

   This backend implements payments using the Advanced Integration Method (AIM) from `Authorize.Net <https://www.authorize.net/>`_.

   :param login_id: Your API Login ID assigned by Authorize.net
   :param transaction_key: Your unique Transaction Key assigned by Authorize.net
   :param endpoint: The API endpoint to use. To test using staging environment, use ``'https://test.authorize.net/gateway/transact.dll'`` instead

Example::

   # use staging environment
   PAYMENT_VARIANTS = {
       'authorizenet': ('payments.authorizenet.AuthorizeNetProvider', {
           'login_id': '1234login',
           'transaction_key': '1234567890abcdef',
           'endpoint': 'https://test.authorize.net/gateway/transact.dll'})}


Dotpay
------

.. class:: payments.dotpay.DotpayProvider(seller_id, pin[, channel=0[, lock=False], lang='pl'])

   This backend implements payments using a popular Polish gateway, `Dotpay.pl <http://www.dotpay.pl>`_.

   Due to API limitations there is no support for transferring purchased items.


   :param seller_id: Seller ID assigned by Dotpay
   :param pin: PIN assigned by Dotpay
   :param channel: Default payment channel (consult reference guide)
   :param lang: UI language
   :param lock: Whether to disable channels other than the default selected above

Example::

   # use defaults for channel and lang but lock available channels
   PAYMENT_VARIANTS = {
       'dotpay': ('payments.dotpay.DotpayProvider', {
           'seller_id': '123',
           'pin': '0000',
           'lock': True})}


Google Wallet
-------------

.. class:: payments.wallet.GoogleWalletProvider(seller_id, seller_secret[, library='https://wallet.google.com/inapp/lib/buy.js'])

   This backend implements payments using `Google Wallet <https://developers.google.com/commerce/wallet/digital/>`_ for digital goods API.

   :param seller_id: Seller ID assigned by Google Wallet
   :param seller_secret: Seller secret assigned by Google Wallet
   :param library: The API library to use. To test using sandbox, use ``'https://sandbox.google.com/checkout/inapp/lib/buy.js'`` instead

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

E.g: ``https://example.com/payments/process/wallet``


Paypal
------

.. class:: payments.paypal.PaypalProvider(client_id, secret[, endpoint='https://api.paypal.com'])

   This backend implements payments using `PayPal.com <https://www.paypal.com/>`_.

   :param client_id: Client ID assigned by PayPal or your email address
   :param secret: Secret assigned by PayPal
   :param endpoint: The API endpoint to use. To test using sandbox, use ``'https://api.sandbox.paypal.com'`` instead

Example::

   # use sandbox
   PAYMENT_VARIANTS = {
       'paypal': ('payments.paypal.PaypalProvider', {
           'client_id': 'user@example.com',
           'secret': 'iseedeadpeople',
           'endpoint': 'https://api.sandbox.paypal.com'})}

.. class:: payments.paypal.PaypalCardProvider(client_id, secret, endpoint='https://api.paypal.com')

   This backend implements payments using `PayPal.com <https://www.paypal.com/>`_ but the credit card data is collected by your site.

   Parameters are identical to those of :class:`payments.paypal.PaypalProvider`.

Example::

   PAYMENT_VARIANTS = {
       'paypal': ('payments.paypal.PaypalCardProvider', {
           'client_id': 'user@example.com',
           'secret': 'iseedeadpeople'})}


Sage Pay
--------

.. class:: payments.sagepay.SagepayProvider(vendor, encryption_key[, endpoint='https://live.sagepay.com/gateway/service/vspform-register.vsp'])

   This backend implements payments using `SagePay.com <https://www.sagepay.com/>`_ Form API.

   Purchased items are not currently transferred.

   :param vendor: Your vendor code
   :param encryption_key: Encryption key assigned by Sage Pay
   :param endpoint: The API endpoint to use. To test using simulator, use ``'https://test.sagepay.com/Simulator/VSPFormGateway.asp'`` instead

Example::

   # use simulator
   PAYMENT_VARIANTS = {
       'sage': ('payments.sagepay.SagepayProvider', {
           'vendor': 'example',
           'encryption_key': '1234567890abcdef',
           'endpoint': 'https://test.sagepay.com/Simulator/VSPFormGateway.asp'})}

