django-payments
===============

This library is a Django app for handling payments with a few different payment
providers.

It includes support for a few different payment providers using a unified API.

General design
--------------

A single abstract model is included: :class:`payments.models.BasePayment`.
Applications using this library need to subclass it and implement a few specific
method. It is also possible to domain-specific fields that the may be required
(e.g.: foreign keys to a purchase, or user).

Contents:

.. toctree::
   :maxdepth: 2

   install.rst
   usage.rst
   refund.rst
   preauth.rst
   modules.rst
   api.rst
   changelog.rst
