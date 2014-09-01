.. _capture-payments:

Capture payments later
======================

Some gateways offer a two-step payment method known as Authorization & Capture, which allows you to collect the payment at a later time. To use this payment type, do the following:

1. Set ``capture`` parameter to ``False`` in the configuration of your payment backend, for example::

      # settings.py
      PAYMENT_VARIANTS = {
          'default': ('payments.dummy.DummyProvider', {
              'capture': False})}


2. To capture the payment, call the ``capture()`` method on the :class:`Payment` instance::

    >>> from payments import get_payment_model
    >>> Payment = get_payment_model()
    >>> payment = Payment.objects.get()
    >>> payment.capture()

  By default, the total amount will be captured, but you can capture a lower amount, by providing the ``amount`` parameter::

    >>> from decimal import Decimal
    >>> payment.capture(amount=Decimal(10.0))


3. To release the payment, call the ``release()`` method on your :class:`Payment` instance::

    >>> from payments import get_payment_model
    >>> Payment = get_payment_model()
    >>> payment = Payment.objects.get()
    >>> payment.release()

