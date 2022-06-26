Installation
============

Install the package
-------------------

.. code-block:: bash

  $ pip install django-payments

Most providers have additional dependencies. For example, if using stripe, you
should run:


.. code-block:: bash

  $ pip install "django-payments[stripe]"

Multiple providers can be specified comma-separated, e.g.:

.. code-block:: bash

  $ pip install "django-payments[mercadopago,stripe]"

.. hint::

  Use quotes as above to prevent your shell from parsing the square brackets.

.. versionchanged:: 0.15

   Each provider now has extra/optional dependencies. Previously, dependencies
   for **all** providers were installed by default.

Configure Django
----------------

``payments`` needs to be registered as a Django app by adding it to
``settings.py``:

    .. code-block:: python

      INSTALLED_APPS = [
        ...
        "payments",
        ...
      ]

There is no strong requirement for it to be listed first nor last.

Add the callback processor to your URL router (``urls.py``).

    .. code-block:: python

      # urls.py
      from django.conf.urls import include, path

      urlpatterns = [
          path('payments/', include('payments.urls')),
      ]

This includes two sets of URLs:

- Views (endpoints) where notifications will be received from payment
  providers. These **must** be exposed properly for the provider to notify us
  of any payment. Note that these notifications may be delivered _after_ the
  user has navigated away from the website.
- Views where users are directed after completing a payment. Usually, once the
  user has completed a flow at the payment provider's website, their browser
  will be redirected to one of these views and ``POST`` some additional data.
  These views parse this data, communicate with the provider (if a necessary)
  and then redirect the user to a view of your choosing.

None of these views render any "pages" that your users might every see.

.. _settings:

Additional Django settings
--------------------------

The following settings are mandatory, as well as ``PAYMENT_MODEL`` (more on
this later in :ref:`PAYMENT_MODEL`).

.. code-block:: python

  # This can be a string or callable, and should return a base host that
  # will be used when receiving callbacks and notifications from payment
  # providers.
  #
  # Keep in mind that if you use `localhost`, external servers won't be
  # able to reach you for webhook notifications.
  PAYMENT_HOST = 'localhost:8000'

  # Whether to use TLS (HTTPS). If false, will use plain-text HTTP.
  # Defaults to ``not settings.DEBUG``.
  PAYMENT_USES_SSL = False

The following setting is optional, and reserved for advanced usages:

.. code-block:: python

  # Callable to retrieve payment provider instance
  #
  # This is an advanced setting. It is required if defining provider
  # credentials in the settings file is unsuitable. Implementations may choose
  # to read provider credentials from the database or any other source that's
  # suitable.
  #
  # Alternatively, you can provide a callable that takes two arguments:
  # variant (string) and an optional payment (BasePayment).
  # The callback has to return an instance of the desired payment provider.
  #
  # For inspiration, see the payments.core.payment_factory function, which
  # retrieves the variant from the above dictionary.
  PAYMENT_VARIANT_FACTORY = "mypaymentapp.provider_factory"
