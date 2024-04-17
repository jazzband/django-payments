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
from .core import provider_factory

logger = logging.getLogger(__name__)


class PaymentAttributeProxy:
    def __init__(self, payment):
        self._payment = payment
        super().__init__()

    def __getattr__(self, item):
        data = json.loads(self._payment.extra_data or "{}")
        try:
            return data[item]
        except KeyError as e:
            raise AttributeError(*e.args) from e

    def __setattr__(self, key, value):
        if key == "_payment":
            return super().__setattr__(key, value)
        try:
            data = json.loads(self._payment.extra_data)
        except ValueError:
            data = {}
        data[key] = value
        self._payment.extra_data = json.dumps(data)
        return None


class BaseSubscription(models.Model):
    token = models.CharField(
        _("subscription token/id"),
        help_text=_("Token/id used to identify subscription by provider"),
        max_length=255,
        default=None,
        null=True,
        blank=True,
    )
    payment_provider = models.CharField(
        _("payment provider"),
        help_text=_("Provider variant, that will be used for payment renewal"),
        max_length=255,
        default=None,
        null=True,
        blank=True,
    )
    subscribtion_data = models.JSONField(
        _("subscription data"),
        help_text=_("Provider-specific data associated with subscription"),
        default=dict,
    )

    class TimeUnit(enum.Enum):
        year = "year"
        month = "month"
        day = "day"

    def set_recurrence(self, token: str, **kwargs):
        """
        Sets token and other values associated with subscription recurrence
        Kwargs can contain provider-specific values
        """
        self.token = token
        self.subscribtion_data = kwargs

    def get_period(self) -> int:
        raise NotImplementedError

    def get_unit(self) -> TimeUnit:
        raise NotImplementedError

    def cancel(self):
        """
        Cancel the subscription by provider
        Used by providers, that use provider initiated subscription workflow
        Implementer is responsible for cancelling the subscription model

        Raises PaymentError if the cancellation didn't pass through
        """
        provider = provider_factory(self.variant)
        provider.cancel_subscription(self)

    class Meta:
        abstract = True


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

    def __str__(self):
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

    def change_status(self, status: PaymentStatus | str, message=""):
        """
        Updates the Payment status and sends the status_changed signal.
        """
        from .signals import status_changed

        self.status = status  # type: ignore[assignment]
        self.message = message
        self.save(update_fields=["status", "message"])
        status_changed.send(sender=type(self), instance=self)

    def change_fraud_status(self, status: PaymentStatus, message="", commit=True):
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

    def get_payment_url(self) -> str:
        """
        Get the url the view that handles the payment
        (payment_details() in documentation)
        For now used only by PayU provider to redirect users back to CVV2 form
        """
        raise NotImplementedError

    def get_subscription(self) -> Optional[BaseSubscription]:
        """
        Returns subscription object associated with this payment
        or None if the payment is not recurring
        """
        return None

    def is_recurring(self) -> bool:
        return self.get_subscription() is not None

    def autocomplete_with_subscription(self):
        """
        Complete the payment with subscription

        If the provider uses workflow such that the payments are initiated from
        implementer's side.
        Call this function right before the subscription end to
        make a new subscription payment.

        Throws RedirectNeeded if there is problem with the payment
        that needs to be solved by user
        """
        provider = provider_factory(self.variant)
        provider.autocomplete_with_subscription(self)

    def capture(self, amount=None):
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

    def release(self):
        """Release a pre-authorized payment.

        Note that not all providers support this method.
        """
        if self.status != PaymentStatus.PREAUTH:
            raise ValueError("Only pre-authorized payments can be released.")
        provider = provider_factory(self.variant, self)
        provider.release(self)
        self.change_status(PaymentStatus.REFUNDED)

    def refund(self, amount=None):
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
                self.id,
                amount,
                self.captured_amount,
            )
        self.captured_amount -= amount
        if self.captured_amount <= 0 and self.status != PaymentStatus.REFUNDED:
            self.change_status(PaymentStatus.REFUNDED)
        self.save()

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
