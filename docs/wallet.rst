Wallet-Based Recurring Payments
================================

Overview
--------

The wallet interface enables server-initiated recurring payments, where your application
controls when to charge stored payment methods. This is different from subscription-based
systems where the payment provider manages the billing cycle.

**Use cases:**

* Subscription services with custom billing logic
* Usage-based billing with variable amounts
* Flexible payment schedules (e.g., proration, pausing)
* Multiple payment attempts with custom retry logic

**Supported providers:**

* PayU (via `django-payments-payu <https://github.com/PetrDlouhy/django-payments-payu>`_)
* Stripe (via PaymentIntent API)
* Adyen (via tokenization)
* Any provider supporting card tokenization

Architecture
------------

The wallet system consists of three components:

1. **BaseWallet** - Abstract model for storing payment method tokens
2. **Payment.get_renew_token() / set_renew_token()** - Token management interface
3. **Provider.autocomplete_with_wallet()** - Server-initiated charging

Flow Diagram
~~~~~~~~~~~~

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

    Recurring Payment (Server-Initiated):
    ┌─────────────────┐
    │ Your server     │
    │ creates Payment │
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

Implementation Guide
--------------------

Step 1: Create Wallet Model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Extend ``BaseWallet`` in your application:

.. code-block:: python

    from django.db import models
    from payments.models import BaseWallet

    class Wallet(BaseWallet):
        user = models.ForeignKey(User, on_delete=models.CASCADE)
        payment_provider = models.CharField(max_length=50)

        def payment_completed(self, payment):
            """Called after successful payment."""
            super().payment_completed(payment)  # Activates wallet
            # Add custom logic (notifications, logging, etc.)
            self.user.email_user("Payment successful", ...)

Step 2: Link Payment to Wallet
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Add wallet reference to your Payment model:

.. code-block:: python

    from payments.models import BasePayment

    class Payment(BasePayment):
        wallet = models.ForeignKey(
            Wallet,
            on_delete=models.SET_NULL,
            null=True,
            blank=True,
            related_name="payments",
        )

        def get_renew_token(self):
            """Retrieve token from wallet."""
            if self.wallet and self.wallet.status == WalletStatus.ACTIVE:
                return self.wallet.token
            return None

        def set_renew_token(self, token, **kwargs):
            """Store token in wallet."""
            if not self.wallet:
                self.wallet = Wallet.objects.create(
                    user=self.user,  # Your user reference
                    payment_provider=self.variant
                )
                self.save()

            self.wallet.token = token
            self.wallet.extra_data.update(kwargs)
            self.wallet.activate()

Step 3: Configure Payment Variant
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Add recurring payment variant to settings:

.. code-block:: python

    # settings.py
    PAYMENT_VARIANTS = {
        'stripe-recurring': (
            'payments.stripe.StripeProviderV3',
            {
                'api_key': STRIPE_SECRET_KEY,
                'recurring_payments': True,
            }
        ),
        'payu-recurring': (
            'payments_payu.provider.PayuProvider',
            {
                'pos_id': PAYU_POS_ID,
                'client_secret': PAYU_CLIENT_SECRET,
                'recurring_payments': True,
                'store_card': True,
            }
        ),
    }

Step 4: First Payment (Setup)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create payment for initial setup:

.. code-block:: python

    # views.py
    def subscribe_user(request):
        # Create wallet
        wallet = Wallet.objects.create(
            user=request.user,
            payment_provider='stripe-recurring'
        )

        # Create payment
        payment = Payment.objects.create(
            variant='stripe-recurring',
            total=Decimal('20.00'),
            currency='USD',
            wallet=wallet,
            # ... other fields
        )

        # Redirect to payment form
        return redirect('payment_form', payment_id=payment.id)

After successful payment, the provider automatically calls ``set_renew_token()``
to store the payment method token.

Step 5: Recurring Charges
~~~~~~~~~~~~~~~~~~~~~~~~~~

Charge stored payment method:

.. code-block:: python

    # tasks.py (e.g., Celery task)
    def charge_subscription(user_id):
        user = User.objects.get(id=user_id)
        wallet = user.wallet_set.filter(status=WalletStatus.ACTIVE).first()

        if not wallet:
            return  # No active wallet

        # Create payment
        payment = Payment.objects.create(
            variant=wallet.payment_provider,
            total=Decimal('20.00'),
            currency='USD',
            wallet=wallet,
            # ... other fields
        )

        try:
            # Charge stored payment method
            payment.autocomplete_with_wallet()
        except RedirectNeeded as e:
            # User interaction required (3D Secure, etc.)
            # Send email with link to e.url
            send_3ds_email(user, e.url)
        except PaymentError as e:
            # Payment failed
            handle_failed_payment(user, e)

Alternative: Without Wallet FK
------------------------------

If you have existing architecture (like BlenderKit's ``RecurringUserPlan``),
you can override token methods without using wallet FK:

.. code-block:: python

    class Payment(BasePayment):
        # No wallet FK needed

        def get_renew_token(self):
            """Get token from your existing model."""
            try:
                recurring = self.order.user.userplan.recurring
                return recurring.token
            except AttributeError:
                return None

        def set_renew_token(self, token, **kwargs):
            """Store token in your existing model."""
            recurring = self.order.user.userplan.recurring
            recurring.token = token
            recurring.card_expire_year = kwargs.get('card_expire_year')
            # ... store other fields
            recurring.save()

This allows wallet-based providers to work with any storage mechanism.

Provider Implementation
-----------------------

For provider developers implementing wallet support:

.. code-block:: python

    from payments.core import BasicProvider
    from payments import PaymentStatus, RedirectNeeded, PaymentError

    class MyWalletProvider(BasicProvider):
        def __init__(self, recurring_payments=False, **kwargs):
            super().__init__(**kwargs)
            self.recurring_payments = recurring_payments

        def autocomplete_with_wallet(self, payment):
            """Charge stored payment method."""
            # 1. Get token
            token = payment.get_renew_token()
            if not token:
                raise PaymentError("No payment method token found")

            # 2. Charge via provider API
            try:
                result = self.api.charge(
                    amount=payment.total,
                    currency=payment.currency,
                    payment_method=token,
                )
            except ProviderError as e:
                payment.change_status(PaymentStatus.REJECTED)
                raise PaymentError(str(e))

            # 3. Update payment
            payment.transaction_id = result.id
            payment.captured_amount = payment.total

            # 4. Handle result
            if result.status == 'succeeded':
                payment.change_status(PaymentStatus.CONFIRMED)
                self._finalize_wallet_payment(payment)  # Triggers wallet.payment_completed()
            elif result.requires_action:
                raise RedirectNeeded(result.redirect_url)
            else:
                payment.change_status(PaymentStatus.REJECTED)

        def erase_wallet(self, wallet):
            """Delete payment method from provider."""
            if wallet.token:
                self.api.delete_payment_method(wallet.token)
            super().erase_wallet(wallet)  # Mark as erased

Best Practices
--------------

**Security**

* Never log or display full payment tokens
* Use HTTPS for all payment-related requests
* Implement rate limiting on payment attempts
* Validate payment amounts server-side

**Error Handling**

* Implement retry logic with exponential backoff
* Send notifications on failed payments
* Provide user-friendly error messages
* Log all payment attempts for debugging

**User Experience**

* Show card details (last 4 digits, expiry) from ``wallet.extra_data``
* Allow users to update payment method (zero-dollar auth)
* Send email before charging (especially after failures)
* Provide clear cancellation process

**Testing**

* Test with provider's sandbox/test mode
* Test 3D Secure flows (RedirectNeeded)
* Test expired cards
* Test declined payments
* Test network failures

Example: Complete Subscription System
--------------------------------------

.. code-block:: python

    # models.py
    class Subscription(models.Model):
        user = models.ForeignKey(User, on_delete=models.CASCADE)
        wallet = models.ForeignKey(Wallet, on_delete=models.SET_NULL, null=True)
        plan = models.CharField(max_length=50)
        amount = models.DecimalField(max_digits=9, decimal_places=2)
        next_billing_date = models.DateField()
        status = models.CharField(max_length=20)

    # tasks.py (Celery)
    @app.task
    def process_recurring_payments():
        """Daily task to charge subscriptions."""
        today = date.today()
        subscriptions = Subscription.objects.filter(
            next_billing_date=today,
            status='active',
            wallet__status=WalletStatus.ACTIVE
        )

        for subscription in subscriptions:
            payment = Payment.objects.create(
                variant=subscription.wallet.payment_provider,
                total=subscription.amount,
                currency='USD',
                wallet=subscription.wallet,
            )

            try:
                payment.autocomplete_with_wallet()
                subscription.next_billing_date += timedelta(days=30)
                subscription.save()
            except RedirectNeeded as e:
                send_3ds_email(subscription.user, e.url)
            except PaymentError:
                subscription.status = 'payment_failed'
                subscription.save()
                send_failed_payment_email(subscription.user)

API Reference
-------------

BaseWallet
~~~~~~~~~~

.. class:: BaseWallet

    Abstract model for storing payment method tokens.

    .. attribute:: token

        Payment method token/ID from provider (CharField, max 255, nullable)

    .. attribute:: status

        Wallet status: PENDING, ACTIVE, or ERASED (CharField)

    .. attribute:: extra_data

        Provider-specific data like card details (JSONField)

    .. method:: payment_completed(payment)

        Called after successful payment. Default: activates wallet.

    .. method:: activate()

        Mark wallet as active and ready for charges.

    .. method:: erase()

        Mark wallet as erased (no longer usable).

BasePayment Methods
~~~~~~~~~~~~~~~~~~~

.. method:: get_renew_token()

    Returns payment method token for recurring charges.
    Default: returns None. Override in subclass.

.. method:: set_renew_token(token, card_expire_year=None, card_expire_month=None, card_masked_number=None, automatic_renewal=True)

    Stores payment method token after successful payment.
    Default: does nothing. Override in subclass.

.. method:: autocomplete_with_wallet()

    Charges stored payment method (server-initiated).
    Raises RedirectNeeded if user interaction required.

BasicProvider Methods
~~~~~~~~~~~~~~~~~~~~~

.. method:: autocomplete_with_wallet(payment)

    Provider implementation of wallet-based charging.
    Must be implemented by wallet-supporting providers.

.. method:: erase_wallet(wallet)

    Deletes/detaches payment method from provider system.
    Default: marks wallet as ERASED.

.. method:: _finalize_wallet_payment(payment, wallet=None)

    Internal helper to trigger wallet.payment_completed().
    Call after successful charge.

Troubleshooting
---------------

**"No payment method token found"**

* Ensure ``get_renew_token()`` is implemented
* Check wallet status is ACTIVE
* Verify token was stored after first payment

**RedirectNeeded exception**

* User interaction required (3D Secure, CVV)
* Send email with redirect URL
* User completes action, webhook updates payment

**Payment fails silently**

* Check provider logs/dashboard
* Verify webhook endpoint is accessible
* Ensure ``_finalize_wallet_payment()`` is called

**Wallet not activating**

* Check ``payment_completed()`` is called
* Verify payment status is CONFIRMED
* Override ``payment_completed()`` if needed

See Also
--------

* :doc:`usage` - Basic payment flow
* :doc:`webhooks` - Webhook handling
* :doc:`preauth` - Pre-authorization
* `django-payments-payu <https://github.com/PetrDlouhy/django-payments-payu>`_ - Example wallet implementation

