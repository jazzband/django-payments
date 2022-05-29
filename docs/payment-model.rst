The ``Payment`` class
=====================

Create a ``Payment`` class
--------------------------

django-payments ship an abstract :class:`payments.models.BasePayment` class.
Individual projects need to subclass it and implement a few methods and may
include any extra payment-related fields on this model. It is also possible to
add a foreign key to an existing purchase or order model.

The following instance methods are required:

.. automethod:: payments.models.BasePayment.get_failure_url

.. automethod:: payments.models.BasePayment.get_success_url

.. automethod:: payments.models.BasePayment.get_purchased_items

Example implementation
......................

    .. code-block:: python

      # mypaymentapp/models.py
      from decimal import Decimal

      from payments import PurchasedItem
      from payments.models import BasePayment

      class Payment(BasePayment):

          def get_failure_url(self) -> str:
              # Return a URL where users are redirected after
              # they fail to complete a payment:
              return f"http://example.com/payments/{self.pk}/failure"

          def get_success_url(self) -> str:
              # Return a URL where users are redirected after
              # they successfully complete a payment:
              return f"http://example.com/payments/{self.pk}/success"

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
passing POST data to :meth:`~.BasePayment.get_form`:

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

          return TemplateResponse(
              request,
              'payment.html',
              {'form': form, 'payment': payment}
          )

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

Once users have completed a payment, they will be redirected to the URl
returned by :meth:`~.BasePayment.get_success_url` or
:meth:`~.BasePayment.get_failure_url`.

Mutating a ``Payment`` instance
-----------------------------

When operating ``Payment`` instances, care should be take to only save
changes atomically. If a model is loaded into memory, mutated, and then saved
back to the database it is possible to overwrite concurrent changes made by
handling a notification from the payment processor. Keep in mind that most
processors are likely implement "at least once" notification delivery.

In general, you should either:

- Use atomic updates only specifying the relevant fields. For example, if the
  application-local ``Payment`` class has a custom field named
  ``discount_card_code``, use
  ``BasePayment.objects.filter(pk=payment_id).update(discount_card_code="123XYZ")``.
  This is the recommended approach.
- Lock the database row while mutating a python instance of ``BasePayment`` (may
  negatively affect performance at scale).

.. _PAYMENT_MODEL:

Registering the ``Payment`` class
---------------------------------

Once the ``Payment`` class has been implemented, it needs to be registered as
the payment model for an application. This is done by adding a variable to the
``settings.py`` file. E.g.:

.. code-block:: python

  # A dotted path to the Payment class.
  PAYMENT_MODEL = 'mypaymentapp.models.Payment'
