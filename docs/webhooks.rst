.. _webhooks:

Webhooks
=================


You can also set up the Webhook to receive status updates directly from Stripe.
To use this you need to set the option PAYMENT_HOST to match the public URL for your Django Project


Stripe
-------

Setting up Webhooks in Stripe
To receive payment notifications and updates from Stripe, you need to set up webhooks. Follow these steps to configure webhooks in your Stripe Dashboard:

* Log in to your Stripe Dashboard <https://dashboard.stripe.com/>__.
* In the left sidebar, click on "Developers" and then select "Webhooks".
* Click on the "+ Add endpoint" button to create a new webhook listener.

* In the "Endpoint URL" field, enter the URL for the Stripe variant in your Django Payments application. This URL should be the endpoint where Stripe will send the webhook events. Make sure the URL is accessible from the internet.
    Example: https://your-app.com/payments/stripe/
* From the "Events to send" dropdown, choose the specific events you want to receive notifications for. You need these events:
    * checkout.session.async_payment_failed
    * checkout.session.async_payment_succeeded
    * checkout.session.completed
    * checkout.session.expired
* Click on the "Add endpoint" button to save your webhook listener.
* Once the webhook is created, you will see its details in the "Webhooks" section. Take note of the "Signing secret" provided by Stripe as you will need it later when configuring the webhook handler in your Django application.
* Test the webhook by sending a test event to your endpoint. Stripe provides a "Send test webhook" button on the webhook details page. Use this feature to ensure your endpoint is correctly configured and can receive and process events from Stripe.

Note: It's essential to secure your webhook endpoint and verify the authenticity of the events sent by Stripe. In your Django Payments application, you'll need to implement a webhook handler that validates the signature of incoming requests using the signing secret provided by Stripe.

Make sure to replace https://your-app.com/payments/stripe/ with the actual URL for your Stripe webhook endpoint.
