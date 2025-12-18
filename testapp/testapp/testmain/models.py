from __future__ import annotations

from django.db import models

from payments import PurchasedItem
from payments import WalletStatus
from payments.models import BasePayment
from payments.models import BaseSubscription
from payments.models import BaseWallet


class Wallet(BaseWallet):
    """
    Example wallet implementation for recurring payments.

    This demonstrates how to extend BaseWallet for your application.
    In a real application, you would add a ForeignKey to your User model.
    """

    payment_provider = models.CharField(
        max_length=50,
        help_text="Payment variant name (e.g., 'stripe-recurring', 'payu-recurring')",
    )
    # In real app: user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        app_label = "testmain"

    def payment_completed(self, payment):
        """Custom logic after successful payment."""
        super().payment_completed(payment)
        # Add your custom logic here (notifications, logging, etc.)


class Subscription(BaseSubscription):
    """
    Example subscription implementation for provider-managed recurring payments.

    This demonstrates how to extend BaseSubscription for your application.
    In a real application, you would add a ForeignKey to your User model
    and fields for plan details.
    """

    payment_provider = models.CharField(
        max_length=50,
        help_text=(
            "Payment variant name (e.g., 'stripe-subscription', 'paypal-subscription')"
        ),
    )
    plan = models.CharField(
        max_length=50,
        default="",
        blank=True,
        help_text="Subscription plan identifier (e.g., 'basic', 'premium')",
    )
    # In real app: user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        app_label = "testmain"

    def subscription_payment_completed(self, payment):
        """Custom logic after each recurring payment."""
        super().subscription_payment_completed(payment)
        # Add your custom logic here (extend service period, notifications, etc.)


class Payment(BasePayment):
    """
    Example payment implementation with wallet and subscription support.

    This demonstrates patterns for both:
    1. Wallet-based recurring payments (variable amounts, app-controlled)
    2. Subscription-based recurring payments (fixed amounts, provider-controlled)
    """

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        help_text="Wallet used for recurring payments",
    )

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        help_text="Subscription for provider-managed recurring payments",
    )

    class Meta:
        app_label = "testmain"

    def get_failure_url(self):
        return "http://localhost:8000/test/payment-failure"

    def get_success_url(self):
        return "http://localhost:8000/test/payment-success"

    def get_purchased_items(self):
        yield PurchasedItem(
            name=self.description,
            sku="BSKV",
            quantity=1,
            price=self.total,
            currency=self.currency,
        )

    def get_renew_token(self):
        """
        Get payment method token for recurring payments.

        This implementation uses the wallet FK. For projects with different
        architecture (e.g., token stored elsewhere), override this method.
        """
        if self.wallet and self.wallet.status == WalletStatus.ACTIVE:
            return self.wallet.token
        return None

    def get_renew_data(self):
        """
        Get payment method data (token and customer_id) for recurring payments.

        Returns dict with 'token' and 'customer_id' needed for server-initiated
        recurring charges. For Stripe, both are required for off_session payments.
        """
        if self.wallet and self.wallet.status == WalletStatus.ACTIVE:
            return {
                "token": self.wallet.token,
                "customer_id": self.wallet.extra_data.get("customer_id"),
            }
        return None

    def set_renew_token(
        self,
        token,
        customer_id=None,
        card_expire_year=None,
        card_expire_month=None,
        card_masked_number=None,
        automatic_renewal=True,
    ):
        """
        Store payment method token and customer_id after successful payment.

        This implementation stores in the wallet. For projects with different
        architecture, override this method.
        """
        if not self.wallet:
            # Create wallet if it doesn't exist (first payment)
            self.wallet = Wallet.objects.create(payment_provider=self.variant)
            self.save(update_fields=["wallet"])

        # Store token and card details
        self.wallet.token = token
        self.wallet.extra_data.update(
            {
                "customer_id": customer_id,
                "card_expire_year": card_expire_year,
                "card_expire_month": card_expire_month,
                "card_masked_number": card_masked_number,
                "automatic_renewal": automatic_renewal,
            }
        )
        self.wallet.save(update_fields=["token", "extra_data"])
        self.wallet.activate()  # Mark as active and ready for use

    def get_subscription(self):
        """
        Get subscription object associated with this payment.

        This implementation uses the subscription FK. For projects with different
        architecture, override this method.
        """
        if hasattr(self, "subscription"):
            return self.subscription
        return None
