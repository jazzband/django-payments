Yolfi
=====

.. autoclass:: payments.yolfi.YolfiProvider

This provider creates one-time hosted Checkout Sessions using the native
`Yolfi Checkout API <https://docs.yolfi.com/en/checkout/api-reference>`_.
It uses the existing provider factory and static webhook callback; no additional
package dependency or callback view is required.

Configuration
-------------

Configure separate API and native-webhook credentials in your application
settings, without putting their values in source control::

    import os

    PAYMENT_VARIANTS = {
        "yolfi": (
            "payments.yolfi.YolfiProvider",
            {
                "api_key": os.environ["YOLFI_API_KEY"],
                "webhook_secret": os.environ["YOLFI_WEBHOOK_SECRET"],
            },
        ),
    }

Include ``payments.urls`` as described in :doc:`webhooks`. Configure a **native**
Yolfi webhook destination for the ``static_process_payment`` URL with variant
``yolfi``. For example, when mounted at ``payments/``, this is
``https://merchant.example.com/payments/process/yolfi/``. Subscribe to
``payment.confirmed`` and use that destination's webhook secret, not the API
key. Stripe-compatible and other transformed webhook formats are not accepted.
See the public `webhook data guide
<https://docs.yolfi.com/en/webhooks/webhook-details>`_ and `signature guide
<https://docs.yolfi.com/en/webhooks/webhook-signatures>`_.

The Payment must be saved (with its generated token), have a server-calculated
``Decimal`` total and use ``USD``, ``EUR``, ``CNY``, ``RUB``, ``INR``, ``TRY``,
``KRW`` or ``JPY``. Totals must fit BasePayment's two-decimal monetary field and
be at least ``0.01``. Values are pricing-currency amounts, never minor units or
token quantities. Success and failure URLs must be absolute HTTP(S) URLs.

Calling ``get_form()`` raises ``RedirectNeeded`` with the HTTPS hosted checkout
URL. ``merchantOrderId`` is the Payment's existing UUID token. The provider does
not send customer details, line items or metadata. ``description`` is optional
and limited to 1,000 characters.

Retries and confirmation
------------------------

Before its first HTTP request the provider saves an immutable checkout request
in ``extra_data``. Network retries use that same request and a stable
``Idempotency-Key`` derived from the Payment token. A validated session snapshot
and its reference are saved before redirecting; ``transaction_id`` contains the
Checkout Session ID. Do not change the total, currency, token or provider of a
Payment once checkout has begun. Changed money/reference data fails closed.

Serialize checkout creation and updates for each Payment in your application,
using a transaction and row lock on a saved Payment. Catch ``RedirectNeeded``
inside that transaction so its expected redirect does not roll back the saved
request/session. If you use concurrent workers, use a backend supporting row
locks. Keep the standard callback view, which already locks the Payment row
inside a transaction; custom views must preserve that boundary. Unit tests check
the existing lock call, but are not database/concurrency integration tests.

The raw request body is authenticated with HMAC-SHA256 and the base64
``X-Yolfi-Signature`` before extracting any routing token. A
``payment.confirmed`` event must have ``status=confirmed``, ``paymentType=ONE_TIME``
and a valid Invoice ID. The signed Checkout Session ID, merchant reference and
pricing currency must match the stored session and current Payment. Only then
is ``captured_amount`` set to the original pricing-currency total and the
Payment confirmed. Webhook ``amount`` is a token quantity; it is deliberately
not used as the fiat receivable. Duplicate confirmations cannot confirm or
capture the same Payment twice; a different Invoice on the same stored session
is rejected. The first signed event ID and Invoice ID are retained in
``extra_data``; the Checkout Session ID remains ``transaction_id``.

Limits
------

``Checkout Session.status=COMPLETED`` means an Invoice was created, not that it
was paid. Browser success/cancel returns and non-final Invoice events never
confirm a Payment. Browser cancellation and overdue/expired Invoice notifications
do not automatically reject it; handle abandonment in your application. The
provider cannot create a replacement attempt on the same Payment: use a new
Payment for a new checkout after expiry. Keep confirmed/cancelled/rejected and
other terminal records for reconciliation; callbacks never revive them.

This is one-time hosted checkout only: no card collection, authorization-only
mode, delayed capture, automatic renewal, refunds, partial payments, manual
status sync or cancellation API is implemented. ``capture=False`` is rejected.
The unsupported ``capture()``, ``release()``, ``refund()`` and ``cancel()`` methods
retain BasicProvider's explicit ``NotImplementedError`` contract. There is no
payment-status polling fallback: a correctly configured signed webhook is
required. Non-2xx HTTP responses, invalid session data and request timeouts raise
``PaymentError`` without accepting payment or exposing upstream response bodies.

Tests
-----

``payments/yolfi/test_yolfi.py`` contains deterministic focused unit tests with
synthetic fixtures and mocked external HTTP/payment collaborators. It covers
native checkout, immutable retries, money/reference correlation, signatures and
tampering, malformed responses, final-only capture, duplicate callbacks,
unsupported operations and the standard static callback's lock boundary.
Under the normal upstream test environment, run::

    python -m pytest payments/yolfi/test_yolfi.py

No live credentials or network are needed. These tests are not a full application
build, real-money test, database concurrency test or upstream CI result.
