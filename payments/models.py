from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

import json
import logging
from uuid import uuid4

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField

from . import FraudStatus
from . import PaymentStatus
from . import PurchasedItem
from . import WalletStatus
from .core import provider_factory

logger = logging.getLogger(__name__)


class PaymentAttributeProxy:
    def __init__(self, payment) -> None:
        self._payment = payment
        super().__init__()

    def __getattr__(self, item):
        data = json.loads(self._payment.extra_data or "{}")
        try:
            return data[item]
        except KeyError as e:
            raise AttributeError(*e.args) from e

    def __setattr__(self, key, value) -> None:
        if key == "_payment":
            return super().__setattr__(key, value)
        try:
            data = json.loads(self._payment.extra_data)
        except ValueError:
            data = {}
        data[key] = value
        self._payment.extra_data = json.dumps(data)
        return None


class BaseWallet(models.Model):
    """A stored payment method that can be charged without the user.

    Optional storage for the wallet interface (see ``docs/wallet.rst``).
    The token becomes usable (ACTIVE) after the first successful payment
    and stays unusable once ERASED.
    """

    token = models.CharField(
        _("wallet token/id"),
        help_text=_("Stored payment method token/ID from the provider"),
        max_length=255,
        default="",
        blank=True,
    )
    status = models.CharField(
        max_length=10, choices=WalletStatus.CHOICES, default=WalletStatus.PENDING
    )
    extra_data = models.JSONField(
        _("extra data"),
        help_text=_("Provider-specific data"),
        default=dict,
    )

    class Meta:
        abstract = True

    def payment_completed(self, payment):
        """Activate a pending wallet after its first confirmed payment."""
        if (
            payment.status == PaymentStatus.CONFIRMED
            and self.status == WalletStatus.PENDING
        ):
            self.status = WalletStatus.ACTIVE
            self.save(update_fields=["status"])

    def activate(self):
        """Mark wallet as active and ready for recurring charges."""
        self.status = WalletStatus.ACTIVE
        self.save(update_fields=["status"])

    def erase(self):
        """Mark wallet as erased (no longer usable)."""
        self.status = WalletStatus.ERASED
        self.save(update_fields=["status"])


class BasePayment(models.Model):
    """
    Represents a single transaction. Each instance has one or more PaymentItem.
    """

    variant = models.CharField(max_length=255)
    #: Transaction status
    status = models.CharField(
        max_length=10, choices=PaymentStatus.CHOICES, default=PaymentStatus.WAITING
    )
    fraud_status = models.CharField(
        _("fraud check"),
        max_length=10,
        choices=FraudStatus.CHOICES,
        default=FraudStatus.UNKNOWN,
    )
    fraud_message = models.TextField(blank=True, default="")
    #: Creation date and time
    created = models.DateTimeField(auto_now_add=True)
    #: Date and time of last modification
    modified = models.DateTimeField(auto_now=True)
    #: Transaction ID (if applicable)
    transaction_id = models.CharField(max_length=255, blank=True)
    #: Currency code (may be provider-specific)
    currency = models.CharField(max_length=10)
    #: Total amount (gross)
    total = models.DecimalField(max_digits=9, decimal_places=2, default="0.0")
    delivery = models.DecimalField(max_digits=9, decimal_places=2, default="0.0")
    tax = models.DecimalField(max_digits=9, decimal_places=2, default="0.0")
    description = models.TextField(blank=True, default="")
    billing_first_name = models.CharField(max_length=256, blank=True)
    billing_last_name = models.CharField(max_length=256, blank=True)
    billing_address_1 = models.CharField(max_length=256, blank=True)
    billing_address_2 = models.CharField(max_length=256, blank=True)
    billing_city = models.CharField(max_length=256, blank=True)
    billing_postcode = models.CharField(max_length=256, blank=True)
    billing_country_code = models.CharField(max_length=2, blank=True)
    billing_country_area = models.CharField(max_length=256, blank=True)
    billing_email = models.EmailField(blank=True)
    billing_phone = PhoneNumberField(blank=True)
    customer_ip_address = models.GenericIPAddressField(blank=True, null=True)
    extra_data = models.TextField(blank=True, default="")
    message = models.TextField(blank=True, default="")
    token = models.CharField(max_length=36, blank=True, default="")
    captured_amount = models.DecimalField(max_digits=9, decimal_places=2, default="0.0")

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return self.variant

    def save(self, **kwargs):
        if not self.token:
            tries = {}  # Stores a set of tried values
            while True:
                token = str(uuid4())
                if (
                    token in tries and len(tries) >= 100
                ):  # After 100 tries we are impliying an infinite loop
                    raise SystemExit("A possible infinite loop was detected")
                if not self.__class__._default_manager.filter(token=token).exists():
                    self.token = token
                    break
                tries.add(token)

        return super().save(**kwargs)

    def change_status(self, status: PaymentStatus | str, message="") -> None:
        """
        Updates the Payment status and sends the status_changed signal.
        """
        from .signals import status_changed

        self.status = status  # type: ignore[assignment]
        self.message = message
        self.save(update_fields=["status", "message"])
        status_changed.send(sender=type(self), instance=self)

    def change_fraud_status(
        self,
        status: PaymentStatus,
        message="",
        commit=True,
    ) -> None:
        available_statuses = [choice[0] for choice in FraudStatus.CHOICES]
        if status not in available_statuses:
            raise ValueError(
                'Wrong status "{}", it should be one of: {}'.format(
                    status, ", ".join(available_statuses)
                )
            )
        self.fraud_status = status  # type: ignore[assignment]
        self.fraud_message = message
        if commit:
            self.save()

    def get_form(self, data=None):
        """Return a form to be rendered to complete this payment.

        Please note that this may raise a :class:`~.RedirectNeeded` exception. In this
        case, the user should be redirected to the supplied URL.

        Note that not all providers support a pure form-based flow; some will
        immediately raise ``RedirectNeeded``.
        """
        provider = provider_factory(self.variant, self)
        return provider.get_form(self, data=data)

    def get_purchased_items(self) -> Iterable[PurchasedItem]:
        """Return an iterable of purchased items.

        This information is sent to the payment processor when initiating the payment
        flow. See :class:`.PurchasedItem` for details.

        Subclasses MUST implement this method.
        """

        return []

    def get_failure_url(self) -> str:
        """URL where users will be redirected after a failed payment.

        Return the URL where users will be redirected after a failed attempt to complete
        a payment. This is usually a page explaining the situation to the user with an
        option to retry the payment.

        Note that the URL may contain the ID of this payment, allowing
        the target page to show relevant contextual information.

        Subclasses MUST implement this method.
        """
        raise NotImplementedError

    def get_success_url(self) -> str:
        """URL where users will be redirected after a successful payment.

        Return the URL where users will be redirected after a successful payment. This
        is usually a page showing a payment summary, though it's application-dependant
        what to show on it.

        Note that the URL may contain the ID of this payment, allowing
        the target page to show relevant contextual information.

        Subclasses MUST implement this method.
        """
        raise NotImplementedError

    def get_process_url(self) -> str:
        return reverse("process_payment", kwargs={"token": self.token})

    def autocomplete_with_wallet(self):
        """Charge the stored payment method for ``self.total``, server-side.

        Performs no authorization checks; the caller decides who is charged
        and how much. Raises :class:`~payments.RedirectNeeded` if the
        provider needs the user after all (e.g. 3-D Secure).
        """
        provider = provider_factory(self.variant)
        provider.autocomplete_with_wallet(self)

    def get_renew_token(self):
        """Return the stored payment method token, or None if none is usable.

        Override to read it from your storage. Return only tokens that may be
        charged (e.g. from an ACTIVE wallet).
        """
        return

    def set_renew_token(self, token, **kwargs):
        """Store a payment method token returned by the provider.

        Override to save it in your storage. Providers may pass extra
        provider-specific metadata as keyword arguments.
        """

    def capture(self, amount=None) -> None:
        """Capture a pre-authorized payment.

        Note that not all providers support this method.
        """
        if self.status != PaymentStatus.PREAUTH:
            raise ValueError("Only pre-authorized payments can be captured.")
        provider = provider_factory(self.variant, self)
        amount = provider.capture(self, amount)
        if amount:
            self.captured_amount = amount
            self.change_status(PaymentStatus.CONFIRMED)

    def release(self) -> None:
        """Release a pre-authorized payment.

        Note that not all providers support this method.
        """
        if self.status != PaymentStatus.PREAUTH:
            raise ValueError("Only pre-authorized payments can be released.")
        provider = provider_factory(self.variant, self)
        provider.release(self)
        self.change_status(PaymentStatus.REFUNDED)

    def refund(self, amount=None) -> None:
        if self.status != PaymentStatus.CONFIRMED:
            raise ValueError("Only charged payments can be refunded.")
        if amount and amount > self.captured_amount:
            raise ValueError("Refund amount can not be greater then captured amount")
        provider = provider_factory(self.variant, self)
        amount = provider.refund(self, amount)
        # If the initial amount is None, the code above has no chance to check whether
        # the actual amount is greater than the captured amount before actually
        # performing the refund. But since the refund has been performed already,
        # raising an exception would just cause inconsistencies. Thus, logging an error.
        if amount > self.captured_amount:
            logger.error(
                "Refund amount of payment %s greater than captured amount: %f > %f",
                self.pk,
                amount,
                self.captured_amount,
            )
        self.captured_amount -= amount
        if self.captured_amount <= 0 and self.status != PaymentStatus.REFUNDED:
            self.change_status(PaymentStatus.REFUNDED)
        self.save()

    def cancel(self):
        """Cancel a payment.

        Only payments that have not been processed can be cancelled.
        For pre-authorized payments, use release() instead.
        For confirmed payments, use refund() instead.

        Note that not all providers support this method.
        """
        if self.status not in [PaymentStatus.WAITING, PaymentStatus.INPUT]:
            raise ValueError("Only waiting or input payments can be cancelled.")
        provider = provider_factory(self.variant, self)
        provider.cancel(self)
        self.change_status(PaymentStatus.CANCELLED)

    @property
    def attrs(self):
        """A JSON-serialised wrapper around `extra_data`.

        This property exposes a a dict or list which is serialised into the `extra_data`
        text field. Usage of this wrapper is preferred over accessing the underlying
        field directly.

        You may think of this as a `JSONField` which is saved to the `extra_data`
        column.
        """
        # TODO: Deprecate in favour of JSONField when we drop support for django 2.2.
        return PaymentAttributeProxy(self)
