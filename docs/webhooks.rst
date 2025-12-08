.. _webhooks:

Webhooks
*********

Webhooks are an essential mechanism for integrating your Django Payments
application with external payment gateways like Stripe, PayPal, or Braintree.
They allow real-time event notifications to be sent to your application without
requiring continuous polling or manual API requests. With webhooks, your
application stays synchronized with payment gateway updates, such as successful
payments, subscription status changes, or refunds.

In the context of Django Payments, webhooks enable payment gateways to send
event notifications directly to your Django application. By configuring the
payment gateway to send these notifications to a specific URL endpoint in your
application, you can create a webhook handler to process these events. This
lets you update your internal state, trigger relevant actions, or send user
notifications based on payment-related events.

URL Structure
=============

The webhook URL structure in django-payments follows this pattern::

   {protocol}://{host}/payments/process/{variant}/

Where:

- ``{protocol}``: Defined in ``PAYMENT_PROTOCOL`` (typically "http" or "https").
- ``{host}``: Defined in ``PAYMENT_HOST``.
- ``{variant}``: The payment provider name as configured in ``PAYMENT_VARIANTS``.

For example, with this configuration:

.. code-block:: python

   PAYMENT_VARIANTS = {
       'stripe': (  # <-- This is your variant name
           'payments.stripe.StripeProviderV3',
           {
               'api_key': 'sk_test_123456',
               'use_token': True,
               'endpoint_secret': 'whsec_123456',
               'secure_endpoint': True
           }
       )
   }

   PAYMENT_HOST = 'your-app.com'
   PAYMENT_PROTOCOL = 'https'

Your webhook URL would be::

   https://your-app.com/payments/process/stripe/

.. note::

   Ensure the URL matches exactly, including the trailing slash. A common cause
   of 404 errors is an incorrect URL pattern or a missing trailing slash.

Stripe Webhooks
===============

Stripe uses **global webhook endpoints** (configured once in dashboard for all payments).

Important: Stripe Test vs Live Mode
------------------------------------

Stripe doesn't have a "sandbox" like PayU. Instead:

- **Test mode:** Uses ``sk_test_*`` API keys - no real charges
- **Live mode:** Uses ``sk_live_*`` API keys - real charges

**Each mode has its own webhooks configured separately in the Stripe Dashboard.**

Setting up Webhooks in Stripe
-----------------------------

**For Test Mode (Development):**

#. Log in to `Stripe Dashboard <https://dashboard.stripe.com/>`_ and switch to **Test mode** (toggle in top right).
#. Navigate to **Developers** → **Webhooks**.
#. Click **Add destination** then choose **Webhook**.
#. Enter webhook URL using your **variant name**::

      https://your-devel-server.com/payments/process/stripe-recurring/

   **Important:** Use the variant name from ``PAYMENT_VARIANTS``, not ``<uuid:token>``

#. Select events (expand sections to find):

   **Checkout section:**
      - ``checkout.session.completed``
      - ``checkout.session.expired``
      - ``checkout.session.async_payment_succeeded``
      - ``checkout.session.async_payment_failed``

   **Payment Intent section** (for recurring payments):
      - ``payment_intent.succeeded``
      - ``payment_intent.payment_failed``
      - ``payment_intent.requires_action``

#. Choose **"Your account"** for event source (not "Connected accounts").
#. Click **Add destination** to save.
#. Copy the **Signing secret** (starts with ``whsec_``) to your settings.

**For Live Mode (Production):**

Repeat the same steps but:
- Switch to **Live mode** in Stripe Dashboard
- Use your production domain in webhook URL
- You'll get a different signing secret

**Configuration:**

.. code-block:: python

   # Test mode (development)
   PAYMENT_VARIANTS = {
       'stripe-recurring': (
           'payments.stripe.StripeProviderV3',
           {
               'api_key': 'sk_test_...',  # Test key
               'endpoint_secret': 'whsec_...',  # Test webhook secret
           }
       )
   }

   # Live mode (production)
   PAYMENT_VARIANTS = {
       'stripe-recurring': (
           'payments.stripe.StripeProviderV3',
           {
               'api_key': 'sk_live_...',  # Live key
               'endpoint_secret': 'whsec_...',  # Live webhook secret
           }
       )
   }

**How Stripe webhooks work:**

Stripe sends all events to the same URL. The payment is identified by
``client_reference_id`` in the webhook payload, which django-payments
automatically extracts using ``get_token_from_request()``.

Testing Webhooks Locally
------------------------

During development, you can use the `Stripe CLI
<https://stripe.com/docs/stripe-cli#install>`_ to test webhooks by forwarding
Stripe events to your local server.

#. Install the Stripe CLI and log in:

   .. code-block:: bash

      stripe login

#. Start listening for events and forward them to your local server:

   .. code-block:: bash

      stripe listen --forward-to localhost:8000/payments/process/stripe/ \
         -e checkout.session.async_payment_failed,checkout.session.async_payment_succeeded,checkout.session.completed,checkout.session.expired

#. In another terminal, trigger test events:

   .. code-block:: bash

      stripe trigger checkout.session.completed

Alternative Webhook Testing Tools
---------------------------------

Apart from Stripe's built-in tools, you can test your webhooks using external
services:

- `Beeceptor <https://beeceptor.com/>`_: A free webhook testing tool that
  allows you to inspect and debug webhook requests before integrating them into
  your application.
- `RequestBin by Pipedream <https://pipedream.com/requestbin>`_: Provides a
  public or private endpoint where you can inspect incoming webhook requests in
  real-time.

These tools can be useful for verifying request payloads and debugging webhook
events outside of your local development environment.

Security Best Practices
-----------------------

.. note::

   Always validate incoming webhook requests to ensure they originate from
   Stripe. Use the signing secret to verify authenticity before processing any
   event.

.. warning::

   Ensure ``PAYMENT_HOST`` and ``PAYMENT_PROTOCOL`` are correctly set in your
   Django settings. If they are misconfigured, webhooks will not work as
   expected.
