.. _capture-payments:

Authorization and capture
=========================

Some gateways offer a two-step payment method known as Authorization & Capture, which allows you to collect the payment manually after the buyer has authorized it. To enable this payment type, you have to set the ``capture`` parameter to ``False`` in the configuration of payment backend::

      # settings.py
      PAYMENT_VARIANTS = {
          'default': ('payments.dummy.DummyProvider', {'capture': False})}


Capturing the payment
---------------------
To capture the payment from the buyer, call the ``capture()`` method on the :class:`Payment` instance::

      >>> from payments import get_payment_model
      >>> Payment = get_payment_model()
      >>> payment = Payment.objects.get()
      >>> payment.capture()

By default, the total amount will be captured. You can capture a lower amount, by providing the ``amount`` parameter::

      >>> from decimal import Decimal
      >>> payment.capture(amount=Decimal(10.0))

.. note::

  Only payments with the ``preauth`` status can be captured.


Releasing the payment
---------------------
To release the payment to the buyer, call the ``release()`` method on your :class:`Payment` instance::

      >>> from payments import get_payment_model
      >>> Payment = get_payment_model()
      >>> payment = Payment.objects.get()
      >>> payment.release()

.. note::

  Only payments with the ``preauth`` status can be released.