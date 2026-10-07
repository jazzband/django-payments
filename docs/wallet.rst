Recurring payments with stored payment methods (wallets)
========================================================

A *wallet* is a stored payment method. During one checkout the user agrees
to future charges and the provider returns a token (a card token at PayU, a
vault token at PayPal, a PaymentMethod id at Stripe). Your server can later
charge that token for any amount, without the user. This is what the
payments industry calls merchant-initiated transactions, or "card on file".

This is not the provider-managed subscription model, where the provider
charges a fixed amount on its own schedule.

The interface
-------------

Providers implement two methods on :class:`~payments.core.BasicProvider`:

``autocomplete_with_wallet(payment)``
    Charge the token from ``payment.get_renew_token()`` for
    ``payment.total``, update the payment status and call
    ``self._finalize_wallet_payment(payment)`` on success. Raise
    :class:`~payments.RedirectNeeded` if the user has to act after all
    (3-D Secure, CVV).

``erase_wallet(token)``
    Revoke the token at the provider.

During the first checkout a wallet-capable provider stores the token with
``payment.set_renew_token(token, **metadata)``. The metadata is
provider-specific, so implementations should accept ``**kwargs``.

Your payment model implements the storage hooks on
:class:`~payments.models.BasePayment`:

``get_renew_token()``
    Return a token that may be charged, or ``None``.

``set_renew_token(token, **metadata)``
    Save the token wherever your application keeps it.

``autocomplete_with_wallet()`` on the payment dispatches to its provider.
It does no authorization checks: your code decides who is charged and how
much. The defaults return ``None`` or do nothing, so existing payment
models and providers keep working unchanged.

BaseWallet (optional)
---------------------

:class:`~payments.models.BaseWallet` is an abstract model you can use as
that storage. It holds the ``token``, provider-specific ``extra_data`` and
a ``status``: ``PENDING`` until the first payment succeeds, then
``ACTIVE``, and ``ERASED`` once revoked.

.. code-block:: python

    from payments import WalletStatus
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

Charging and cancelling
-----------------------

.. code-block:: python

    payment = Payment.objects.create(
        variant="payu-recurring", total=Decimal("14.99"), currency="USD", ...
    )
    try:
        payment.autocomplete_with_wallet()
    except RedirectNeeded as redirect_to:
        ...  # e.g. email the user a link to str(redirect_to)

    # Cancel: revoke at the provider, then mark the wallet erased.
    provider_factory(wallet.payment_provider).erase_wallet(wallet.token)
    wallet.erase()

Implementations
---------------

* `django-payments-payu <https://github.com/PetrDlouhy/django-payments-payu>`_
* PayPal Complete Payments (`#490 <https://github.com/jazzband/django-payments/pull/490>`_)
* Stripe, work in progress (`#467 <https://github.com/jazzband/django-payments/pull/467>`_)
* ``DummyProvider`` in this repository
