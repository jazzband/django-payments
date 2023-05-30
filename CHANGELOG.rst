Changelog
=========

This file contains a brief summary of new features and dependency changes or
releases, in reverse chronological order.

v2.1.0
------
- Stripe backends now sends order_id in the metadata parameter.
- A new ``StripeProviderV3`` has been added using the latest Stripe API.
- Added support for Python 3.11, Django 4.1 and Django 4.2.

v2.0.0
------

- **Breaking**: The `todopago` backend has been dropped. The payment provider
  has [quite suddenly] announced it's shutting down.
- Older versions of ``django-phonenumber-field`` are now also supported. There
  was no intrinsic incompatibility; the pinned version was merely too
  restrictive.
- Various documentation improvements.

v1.0.0
------

So far we've been bumping the minor version each time we introduced breaking
changes. This can result in downstream breakage for tools and setups that
expect semantic versioning.

From now on we'll be using semantic versioning and bump the major version
whenever we introduce any breaking changes. Increasing the major number does
not imply that it's a huge release with a lots of changes; it implies that
there is at least one backwards-incompatible change, or a change that requires
intervention.

In this case we've introduced a new field to the abstract Payment class, so
applications will need to create a new migration to apply it (django's
`makemigrations` should handle this perfectly).

- ``billing_phone`` field added to :class:`~.BasePayment`. A migration will be needed
  since, BasePayment is abstract.
- Added TodoPago provider.
- Dropped support for Python 3.6.
- The provider factory is now configurable. See ``PAYMENT_VARIANT_FACTORY`` in
  the :ref:`settings docs <settings>` for details.
- Fix a PayPal error.

v0.15.1
-------

- Added support for Python 3.10.
- Added support for Django 4.0.
- Fixed bad usage of return URLs for Sofort provider.
- Fixed handling of very long descriptions with Sofort.


v0.15.0
-------

- Support for "Google Wallet" has been dropped. It seems to be dead upstream,
  and all existing links to the documentation and to the JS scripts are broken.
- Added support for Django 3.2.
- Dependencies that are only required for a specific provider have been moved
  to extra (optional) dependencies. See the installation instructions for
  further details.
- Added support for MercadoPago.
- ``suds-jurko`` has been replaced with `suds-community`, since the former
  no longer installs with recent ``setuptools``.

**Errata**

This version changed how the ``status_changed`` works. It now only updates the
affected columns. Code that relied on the implicit save within this function
will likely break. See #309 for discussion on this.

v0.14.0
-------

- Dropped support for all Pythons < 3.6.
- Added support for Python 3.8 and 3.9.
- Added support for Django 3.1
- Improved documentation and started adding some typing hints.
- Added PayU provider.
- Pinned some dependencies to avoid potentially broken scenarios.
- Various code cleanups and minor issues fixed.

The project has also moved to Jazzband between the 0.13.0 and 0.14.0 releases.
The new project location is https://github.com/jazzband/django-payments.

PyPI packages and rtd locations remain the same.
