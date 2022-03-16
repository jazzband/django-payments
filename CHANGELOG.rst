Changelog
=========

This file contains a brief summary of new features and dependency changes or
releases, in reverse chronological order.

v0.16.0
-------

- ``billing_phone`` field added to :class:`~.BasePayment`. A migration will be needed
  since, BasePayment is abstract.
- Added TodoPago provider.
- Dropped support for Python 3.6.

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
