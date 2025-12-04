from __future__ import annotations

from django.db import models

from payments import PurchasedItem
from payments import WalletStatus
from payments.models import BasePayment
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

    def payment_completed(self, payment):
        """Custom logic after successful payment."""
        super().payment_completed(payment)
        # Add your custom logic here (notifications, logging, etc.)


class Payment(BasePayment):
    """
    Example payment implementation with wallet support.

    This demonstrates two patterns for wallet integration:
    1. Direct FK to Wallet (simple, works out of box)
    2. Override get_renew_token/set_renew_token (flexible, for complex cases)
    """

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        help_text="Wallet used for recurring payments",
    )

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

    def set_renew_token(
        self,
        token,
        card_expire_year=None,
        card_expire_month=None,
        card_masked_number=None,
        automatic_renewal=True,
    ):
        """
        Store payment method token after successful payment.

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
                "card_expire_year": card_expire_year,
                "card_expire_month": card_expire_month,
                "card_masked_number": card_masked_number,
                "automatic_renewal": automatic_renewal,
            }
        )
        self.wallet.activate()  # Mark as active and ready for use
