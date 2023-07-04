django-payments
===============

This library is a Django app for receiving payments with a few different payment
providers.

When using ``django-payments``, you install and configure a Django
application/library exposes, and the library handles all the communication with
the payment processor. The most obvious use case is implementing online
payments on e-commerce websites, though other unusual cases exist.

Because it provides a common API for different providers, once one provider
is working, it's trivial to add support for others onto a same codebase.

General design
--------------

A single abstract model is included: :class:`payments.models.BasePayment`.
Applications using this library need to subclass it and implement a few specific
method (see the class docs for details). Subclasses can also include their own
additional fields that may be required for payments (e.g.: a foreign key to a
purchase, or a user). This is up to the developer.

Contents:

.. toctree::
   :maxdepth: 2

   install.rst
   payment-model.rst
   variants.rst
   backends.rst
   usage.rst
   refund.rst
   preauth.rst
   webhooks.rst
   api.rst
   changelog.rst
