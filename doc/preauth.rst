.. _capture-payments:

Capture payments later
======================

Some gateways offer a two-step payment method known as Authorization & Capture, which allows you to collect the payment at a later time. To use this payment type, do the following:

#. Set ``capture`` parameter to ``False`` in the configuration of your payment backend, for example::

      # settings.py
      PAYMENT_VARIANTS = {
          'paypal': ('payments.paypal.PaypalProvider', {
              'client_id': 'user@example.com',
              'secret': 'iseedeadpeople',
              'endpoint': 'https://api.sandbox.paypal.com',
              'capture': False})}


#. To capture the payment, call the ``capture()`` method on the :class:`Payment` instance. By default, the total amount will be captured, but you can capture a lower amount, by providing the ``amount`` parameter.

#. To release the payment, call the ``release()`` method on your :class:`Payment` instance.

#. You can refund a captured payment by calling the ``refund()`` method on your :class:`Payment` instance. For partial refund, provide the ``amount`` parameter.

