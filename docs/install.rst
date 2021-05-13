Installation
============

#. Install django-payments

   .. code-block:: bash

      $ pip install django-payments

Note than some providers have additional dependencies. For example, if using
stripe, you should run:


   .. code-block:: bash

      $ pip install "django-payments[stripe]"

#. Add ``payments`` to your ``INSTALLED_APPS``.

#. Add the callback processor to your URL router::

      # urls.py
      from django.conf.urls import include, path

      urlpatterns = [
          path('payments/', include('payments.urls')),
      ]

#. Define a :class:`Payment` model by subclassing :class:`payments.models.BasePayment`::

      # mypaymentapp/models.py
      from decimal import Decimal

      from payments import PurchasedItem
      from payments.models import BasePayment

      class Payment(BasePayment):

          def get_failure_url(self):
              return 'http://example.com/failure/'

          def get_success_url(self):
              return 'http://example.com/success/'

          def get_purchased_items(self):
              # you'll probably want to retrieve these from an associated order
              yield PurchasedItem(name='The Hound of the Baskervilles', sku='BSKV',
                                  quantity=9, price=Decimal(10), currency='USD')

   The :meth:`get_purchased_items` method should return an iterable yielding instances of :class:`payments.PurchasedItem`.

#. Write a view that will handle the payment. You can obtain a form instance by passing POST data to ``payment.get_form()``::

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

      Please note that :meth:`Payment.get_form` may raise a :exc:`RedirectNeeded` exception.

#. Prepare a template that displays the form using its *action* and *method*:

   .. code-block:: html

      <!-- templates/payment.html -->
      <form action="{{ form.action }}" method="{{ form.method }}">
          {% csrf_token %}
          {{ form.as_p }}
          <p><input type="submit" value="Proceed" /></p>
      </form>


#. Configure your ``settings.py``::

      # settings.py
      INSTALLED_APPS = [
          # ...
          'payments']

      PAYMENT_HOST = 'localhost:8000'
      PAYMENT_USES_SSL = False
      PAYMENT_MODEL = 'mypaymentapp.Payment'
      PAYMENT_VARIANTS = {
          'default': ('payments.dummy.DummyProvider', {})}

   Variants are named pairs of payment providers and their configuration.

   .. note::

      Variant names are used in URLs so it's best to stick to ASCII.

   .. note::

      PAYMENT_HOST can also be a callable object.
