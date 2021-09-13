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

Note the quotes to avoid the shell parsing the square brackets.

.. versionchanged:: 0.15

   Each provider now has extra/optional dependencies. Previously, dependencies
   for **all** providers was installed by default.

Configure Django
----------------

Add ``payments`` to your ``settings.py``:

    .. code-block:: python

      INSTALLED_APPS = [
        ...
        "payments",
        ...
      ]

Add the callback processor to your URL router (``urls.py``):

    .. code-block:: python

      # urls.py
      from django.conf.urls import include, path

      urlpatterns = [
          path('payments/', include('payments.urls')),
      ]

Create a "Payment" class
------------------------

You'll need to create your own ``Payment`` model by subclassing the
:class:`payments.models.BasePayment`:: class shipped with this model.

You may include any extra payment-related fields on this model. We suggest
adding a foreign key to your existing purchase or order model.

    .. code-block:: python

      # mypaymentapp/models.py
      from decimal import Decimal

      from payments import PurchasedItem
      from payments.models import BasePayment

      class Payment(BasePayment):

          def get_failure_url(self) -> str:
              # Return a URL where users are redirected after
              # they fail to complete a payment:
              return 'http://example.com/failure/'

          def get_success_url(self) -> str:
              # Return a URL where users are redirected after
              # they successfully complete a payment:
              return 'http://example.com/success/'

          def get_purchased_items(self) -> Iterable[PurchasedItem]:
              # Return items that will be included in this payment.
              yield PurchasedItem(
                  name='The Hound of the Baskervilles',
                  sku='BSKV',
                  quantity=9,
                  price=Decimal(10),
                  currency='USD',
              )

Create a payment view
---------------------

Write a view that will handle the payment. You can obtain a form instance by
passing POST data to ``payment.get_form()``:

    .. code-block:: python

      # mypaymentapp/views.py
      from django.shortcuts import get_object_or_404, redirect
      from django.template.response import TemplateResponse
      from payments import get_payment_model, RedirectNeeded

      def payment_details(request, payment_id):
          payment = get_object_or_404(get_payment_model(), id=payment_id)
          try:
              form = payment.get_form(data=request.POST or None)
          except RedirectNeeded as redirect_to:
              return redirect(str(redirect_to))
          return TemplateResponse(request, 'payment.html',
                                  {'form': form, 'payment': payment})

   .. note::

      Please note that :meth:`Payment.get_form` may raise a
      :exc:`RedirectNeeded` exception. In this case, you need to redirect the
      user to the supplied URL.

Prepare a template that displays the form using its ``action`` and ``method``:

   .. code-block:: html

      <!-- templates/payment.html -->
      <form action="{{ form.action }}" method="{{ form.method }}">
          {% csrf_token %}
          {{ form.as_p }}
          <p><input type="submit" value="Proceed" /></p>
      </form>

Additional Django settings
--------------------------

Additionally, you'll need to configure a few extra settings:

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

      # A dotted path to your Payment class (see above).
      PAYMENT_MODEL = 'mypaymentapp.Payment'

      # Named configuration for your payment provider(s).
      #
      # Each payment processor takes different arguments.
      # This setting is a tuple, where the first element is the variant's name
      # (this is just a local alias), and the second element is a dict with
      # the provider-specific attributes (generally API keys or alike).
      #
      # See Backends for details.
      PAYMENT_VARIANTS = {
          'default': ('payments.dummy.DummyProvider', {})
      }

   .. hint::

      Variant names are used in URLs so it's best to stick to ASCII.
