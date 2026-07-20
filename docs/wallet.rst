Recurring payments with stored payment methods (wallets)
========================================================

What is a wallet?
-----------------

A *wallet* is a stored, chargeable payment method: after one successful
checkout in which the user consents to future charges, the provider hands
back a token (a card token at PayU, a vault payment token at PayPal, a
PaymentMethod id at Stripe) that lets the merchant charge that user again
**server-side, without any user interaction**. The industry calls these
charges *merchant-initiated transactions* ("card on file").

This enables subscription renewals, usage-based billing, installments and
similar flows where **your application decides when and how much to
charge** — the amount is taken from ``payment.total`` and can differ on
every charge.

This is deliberately *not* the provider-managed subscription model (where
the provider charges a fixed amount on a fixed schedule and notifies you
afterwards). Provider-managed subscriptions are out of scope for this
interface.

The interface has two layers:

1. **The contract** (required): a small set of methods on
   :class:`~payments.core.BasicProvider` and hooks on
   :class:`~payments.models.BasePayment` that every wallet-capable
   provider and every integrating application share.
2. **BaseWallet** (optional): a ready-made abstract model implementing
   the storage half of the contract. Use it for new projects; skip it if
   your application already has its own token storage (for example
   `django-plans-payments <https://github.com/PetrDlouhy/django-plans-payments>`_
   stores tokens on its ``RecurringUserPlan``).

Flow
----

.. code-block:: text

    First Payment (Setup):
    ┌─────────────┐
    │ User enters │
    │ card details│
    └──────┬──────┘
           │
           ▼
    ┌─────────────────┐
    │ Provider stores │
    │ payment method  │
    └──────┬──────────┘
           │
           ▼
    ┌──────────────────┐
    │ set_renew_token()│ ← Store token in wallet
    │ wallet.activate()│
    └──────────────────┘

    Recurring Charge (Server-Initiated, any amount):
    ┌─────────────────┐
    │ Your server     │
    │ creates Payment │
    │ with any amount │
    └──────┬──────────┘
           │
           ▼
    ┌──────────────────────┐
    │ payment.             │
    │ autocomplete_with_   │
    │ wallet()             │
    └──────┬───────────────┘
           │
           ▼
    ┌──────────────────────┐
    │ get_renew_token()    │ ← Retrieve token from wallet
    └──────┬───────────────┘
           │
           ▼
    ┌──────────────────────┐
    │ Provider charges     │
    │ stored payment method│
    └──────┬───────────────┘
           │
           ▼
    ┌──────────────────────┐
    │ Update payment status│
    │ wallet.payment_      │
    │ completed()          │
    └──────────────────────┘

Layer 1: the contract
---------------------

Provider side (``BasicProvider``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``autocomplete_with_wallet(payment)``
    Charge the stored payment method server-side for ``payment.total``.
    On success, update the payment status and call
    ``self._finalize_wallet_payment(payment)`` (which triggers
    ``wallet.payment_completed()`` for wallet-model users). If the
    provider requires user interaction to complete the charge (3-D
    Secure, CVV confirmation), raise
    :class:`~payments.RedirectNeeded` with the URL where the user can
    finish the payment — callers are expected to handle it (e.g. by
    emailing the user a link). On a decline, set the payment status to
    ``REJECTED``/``ERROR``.

``erase_wallet(token)``
    Revoke the stored payment method at the provider (delete the card
    token, vault token or detach the payment method). After this, no
    further charges are possible.

During the *first* payment, a wallet-capable provider requests
tokenization from the gateway and, once granted, stores the token via
``payment.set_renew_token(token, **metadata)``. The metadata keyword
arguments are provider-specific (card expiry and masked number for card
providers, ``customer_id`` for Stripe, nothing for PayPal) — integrators
should accept ``**kwargs``.

Integrator side (``BasePayment`` hooks)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``autocomplete_with_wallet()``
    Entry point for your billing code: dispatches to the provider for
    this payment's variant. Performs **no authorization checks** — the
    caller must verify ownership and amounts.

``get_renew_token()`` / ``get_renew_data()``
    Return the stored token (or a dict with the token plus
    provider-specific extras, e.g. ``customer_id``). Return ``None``
    when there is nothing chargeable — in particular, only return tokens
    from *active* wallets, never pending or erased ones.

``set_renew_token(token, **metadata)``
    Store the token wherever your application keeps it (a wallet model,
    a subscription model of your own, ``extra_data``, …).

``get_payment_url()``
    URL of your application's view for this payment. Providers use it as
    the ``RedirectNeeded`` target when a server-initiated charge requires
    user interaction after all (e.g. PayU's CVV / 3-D Secure
    re-verification). Only needed with such providers.

The default implementations return ``None``/do nothing, so a payment
model without recurring support keeps working unchanged.

Layer 2: BaseWallet (optional storage)
--------------------------------------

:class:`~payments.models.BaseWallet` is an abstract model providing the
storage half of the contract: a ``token``, provider-specific
``extra_data`` (JSON), and a lifecycle ``status``:

``PENDING → ACTIVE → ERASED``

The token is not chargeable until the first payment succeeds
(``payment_completed()`` activates a pending wallet), and never again
after erasure. Every known integration reinvented exactly this
lifecycle, which is why it is part of the interface.

.. code-block:: python

    from payments.models import BasePayment, BaseWallet

    class Wallet(BaseWallet):
        user = models.ForeignKey(User, on_delete=models.CASCADE)
        payment_provider = models.CharField(max_length=50)

    class Payment(BasePayment):
        wallet = models.ForeignKey(
            Wallet, null=True, blank=True, on_delete=models.SET_NULL
        )

        def get_renew_token(self):
            if self.wallet and self.wallet.status == WalletStatus.ACTIVE:
                return self.wallet.token
            return None

        def set_renew_token(self, token, **metadata):
            if not self.wallet:
                self.wallet = Wallet.objects.create(
                    user=self.user, payment_provider=self.variant
                )
                self.save(update_fields=["wallet"])
            self.wallet.token = token
            self.wallet.extra_data.update(metadata)
            self.wallet.save(update_fields=["token", "extra_data"])
            self.wallet.activate()

To cancel recurring payments, revoke at the provider first, then mark
the wallet erased:

.. code-block:: python

    provider = provider_factory(wallet.payment_provider)
    provider.erase_wallet(wallet.token)
    wallet.erase()

Charging a stored method
------------------------

.. code-block:: python

    payment = Payment.objects.create(
        variant="payu-recurring",   # a wallet-capable variant
        total=Decimal("14.99"),     # any amount - can differ every cycle
        currency="USD",
        ...,
    )
    try:
        payment.autocomplete_with_wallet()
    except RedirectNeeded as redirect_to:
        # user interaction required (3-D Secure / CVV) -
        # e.g. email the user a link to str(redirect_to)
        ...

Known implementations
---------------------

* `django-payments-payu <https://github.com/PetrDlouhy/django-payments-payu>`_
  (released) — card tokens, raises ``RedirectNeeded`` for CVV/3-D Secure
  re-verification during renewals.
* :class:`~payments.paypal.ppcp.PaypalPPCPProvider` (this repository) —
  vault payment tokens, merchant-initiated renewal charges; the same flow
  runs in production at `Blendkit <https://www.blendkit.com>`_.
* Stripe (`#467 <https://github.com/jazzband/django-payments/pull/467>`_)
  — PaymentMethod + Customer via ``get_renew_data()``, ``off_session``
  PaymentIntents.
* ``DummyProvider`` in this repository — reference implementation for
  tests.
