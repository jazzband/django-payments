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


Creating a New Payment Variant
==============================

Django Payments provides a flexible framework for integrating various payment 
providers into your Django application. This guide will walk you through the 
steps to create a new payment provider in Django Payments.

Step 1: Create a Provider Class
-------------------------------
* Create a new Python module for your provider in the Django Payments project.
* Inside the module, define a class for your provider, inheriting from the base 
`BaseProvider` class provided by Django Payments.

.. code-block:: python
from payments.providers.base import BaseProvider

class MyPaymentProvider(BaseProvider):
def process_data(self, payment, request):
    # Implement webhook processing logic
    pass

def get_form(self, payment, data=None):
    # Implement payment form rendering logic
    pass

def capture(self, payment, amount=None):
    # Implement payment capture logic
    raise NotImplementedError("Capture method not implemented.")

def refund(self, payment, amount=None):
    # Implement payment refund logic
    raise NotImplementedError("Refund method not implemented.")


Implement the mandatory methods specific to your payment provider. Here are the
mandatory methods used by Django Payments:

* process_data(payment, request): This method is responsible for processing 
webhook calls from the payment gateway. It receives a payment object 
representing the payment being processed and the request object. Implement the 
logic to handle the webhook data received from the payment gateway and update
the payment status or perform any necessary actions.

* get_form(payment, data=None): This method is responsible for rendering the 
payment form to be displayed within your Django application. It receives a 
payment  object representing the payment being made and an optional data 
parameter if form submission data is provided. Implement the logic to render 
the payment form, customize it based on your payment gateway requirements, and
handle form submission.

* capture(payment, amount=None): This method is responsible for capturing the 
payment amount. It receives a payment object representing the payment to be 
captured and an optional amount parameter. Implement the logic to interact with
your payment gateway's API and perform the necessary actions to capture the
payment amount. If capturing is not supported by your payment gateway, 
set `capture: false.` to skip capture.

refund(payment, amount=None): This method is responsible for refunding a 
payment. It receives a payment object representing the payment to be refunded
and an optional amount parameter. Implement the logic to interact with your
payment gateway's API and initiate the refund process. If refunding is not
supported by your payment gateway, raise a NotImplementedError.

Make sure to implement these methods in your provider class and handle any
exceptions or errors that may occur during the payment processing or refunding
process.

By implementing these mandatory methods in your provider class, you can
integrate your payment gateway with Django Payments and provide the necessary
functionality to process payments, display payment forms, capture payments, and
handle refunds.

