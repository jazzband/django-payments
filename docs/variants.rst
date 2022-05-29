Configuring variants
====================

django-payment ships with a few :ref:`provider backends <backends>`. Third
party libraries and applications are free to implement others. You may even
implement your own backend if you have users that use some internal payment
system of yours.

Each configured backend is called a "variant". For example, a system may use
two different Stripe accounts. Such a system would configure two variants, both
using the same backend (``payments.stripe.StripeProvider``), but different
credentials.

Variants are configured ``PAYMENT_VARIANTS`` in ``settings.py``. This setting
is a dict, where keys are the variant's name (this is just a local alias) and
the value is a tuple. The tuple contains the dotted path to the backend class,
and a dict with any backend-specific parameters.

See :ref:`provider backends <backends>` for details on each backend and their
required parameters.

Example
-------

.. code-block:: python

  # Named configuration for your payment provider(s).
  PAYMENT_VARIANTS = {
      'default': ('payments.dummy.DummyProvider', {})
  }

.. hint::

  Variant names are used in URLs so it's best to stick to ASCII.
