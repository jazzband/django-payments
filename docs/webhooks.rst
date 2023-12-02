.. _webhooks:

Webhooks
=================


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


Stripe
-------

Setting up Webhooks in Stripe
To receive payment notifications and updates from Stripe, you need to set up
webhooks. Follow these steps to configure webhooks in your Stripe Dashboard:

* Log in to your `Stripe Dashboard <https://dashboard.stripe.com/>`_.
* In the left sidebar, click on **Developers** and then select **Webhooks**.
* Click on the "+ Add endpoint" button to create a new webhook listener.
* In the "Endpoint URL" field, enter the URL for the Stripe variant in your
  Django Payments application. This URL should be the endpoint where Stripe
  will send the webhook events. Make sure the URL is accessible from the
  internet. Example: ``https://your-app.com/payments/stripe/``.
* From the "Events to send" dropdown, choose the specific events you want to
  receive notifications for. You need (at least) these events:
  * checkout.session.async_payment_failed
  * checkout.session.async_payment_succeeded
  * checkout.session.completed
  * checkout.session.expired
* Click on the "Add endpoint" button to save your webhook listener.
* Once the webhook is created, you will see its details in the "Webhooks"
  section. Take note of the "Signing secret" provided by Stripe as you will
  need it later when configuring the webhook handler in your Django application
* Test the webhook by sending a test event to your endpoint. Stripe provides a
  "Send test webhook" button on the webhook details page. Use this feature to
  ensure your endpoint is correctly configured and can receive and process
  events from Stripe.

.. note::

  It's essential to secure your webhook endpoint and verify the authenticity of
  the events sent by Stripe. It's it not recomended to use `secure_endpoint`
  set to false in production.

Make sure to replace **https://your-app.com/payments/stripe/** with the actual
URL for your Stripe webhook endpoint. In this case, ``stripe`` is the `variant`
of the configured provider. E.g.:

.. code-block:: python

  PAYMENT_VARIANTS = {
      'stripe': (  # <-- This value
          'payments.stripe.StripeProviderV3',
          {
              'api_key': 'sk_test_123456',
              'use_token': true,
              'endpoint_secret': 'whsec_123456',
              'secure_endpoint': true
          }
      )
  }
