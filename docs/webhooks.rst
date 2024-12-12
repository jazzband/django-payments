.. _webhooks:

Webhooks
*********

Webhooks are a crucial component in connecting your Django Payments application
with external payment gateways like Stripe, PayPal, or Braintree. They enable
real-time notifications or events from the payment gateway to be sent to your
application, eliminating the need for continuous polling or manual API
requests. With webhooks, your application can stay in sync with payment gateway
updates, such as successful payments, subscription changes, or refunds.

In the context of Django Payments, webhooks provide a means for payment
gateways to send event notifications directly to your Django application. By
configuring the payment gateway to send these notifications to a specific URL
endpoint within your application, you can create a webhook handler that
receives and processes these events. This allows you to update your
application's internal state, trigger actions, or send user notifications based
on payment-related events.


URL Structure
=============
The webhook URL structure in django-payments follows this pattern:

``{protocol}://{host}/payments/process/{variant}/``

Where:

- ``{protocol}``: Configured in ``PAYMENT_PROTOCOL`` (typically "http" or "https")
- ``{host}``: Configured in ``PAYMENT_HOST``
- ``{variant}``: The name you've configured in PAYMENT_VARIANTS


For example, with this configuration:

.. code-block:: python

  PAYMENT_VARIANTS = {
      'stripe': (  # <-- This is your variant name
          'payments.stripe.StripeProviderV3',
          {
              'api_key': 'sk_test_123456',
              'use_token': true,
              'endpoint_secret': 'whsec_123456',
              'secure_endpoint': true
          }
      )
  }

  PAYMENT_HOST = 'your-app.com'
  PAYMENT_PROTOCOL = 'https'

Your webhook URL would be:
``https://your-app.com/payments/process/stripe/``

.. note::

  Make sure the URL matches exactly, including the trailing slash. A common source
  of 404 errors is using the wrong URL pattern or forgetting the trailing slash.


Stripe
======

Setting up Webhooks in Stripe
To receive payment notifications and updates from Stripe, you need to set up
webhooks. Follow these steps to configure webhooks in your Stripe Dashboard:

1. Log in to your `Stripe Dashboard <https://dashboard.stripe.com/>`_.
#. In the left sidebar, click on **Developers** and then select **Webhooks**.
#. Click on the "+ Add endpoint" button to create a new webhook listener.
#. In the "Endpoint URL" field, enter the URL for the Stripe variant in your
   Django Payments application. This URL should follow the pattern:
   ``https://your-app.com/payments/process/{variant}/``, where ``{variant}`` is
   the name you've configured in your PAYMENT_VARIANTS setting.
   For example: ``https://your-app.com/payments/process/stripe/``
#. From the "Events to send" dropdown, choose the specific events you want to
   receive notifications for. You need (at least) these events:

   - checkout.session.async_payment_failed
   - checkout.session.async_payment_succeeded
   - checkout.session.completed
   - checkout.session.expired

#. Click on the "Add endpoint" button to save your webhook listener.
#. Once the webhook is created, you will see its details in the "Webhooks"
   section. Take note of the "Signing secret" provided by Stripe as you will
   need it later when configuring the webhook handler in your Django application
#. Test the webhook by sending a test event to your endpoint. Stripe provides a
   "Send test webhook" button on the webhook details page. Use this feature to
   ensure your endpoint is correctly configured and can receive and process
   events from Stripe.


Testing with Stripe CLI
----------------------

The `Stripe CLI <https://stripe.com/docs/stripe-cli#install>`_ provides a simple
way to test webhooks during local development by forwarding Stripe events to
your local server. After installing and running ``stripe login``, you can start
forwarding events to your local Django server with
``stripe listen --forward-to localhost:8000/payments/process/stripe/``
Use the webhook signing secret provided by the CLI in your development settings.

.. code-block:: bash

   # Start webhook forwarding
   stripe listen --forward-to localhost:8000/payments/process/stripe/

   # In another terminal, trigger test events
   stripe trigger checkout.session.completed


.. note::

  It's essential to secure your webhook endpoint and verify the authenticity of
  the events sent by Stripe. It's not recommended to use `secure_endpoint`
  set to false in production.

.. warning::

  Remember to setup ``PAYMENT_HOST`` and ``PAYMENT_PROTOCOL`` in your settings file,
  otherwise the webhooks won't work, as defined in :ref:`settings`.
