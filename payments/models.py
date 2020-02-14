import enum
import json
from typing import Iterable
from typing import Optional
from typing import Union
from uuid import uuid4

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from . import FraudStatus
from . import PaymentStatus
from . import PurchasedItem
from .core import provider_factory


class PaymentAttributeProxy:
    def __init__(self, payment):
        self._payment = payment
        super().__init__()

    def __getattr__(self, item):
        data = json.loads(self._payment.extra_data or "{}")
        try:
            return data[item]
        except KeyError as e:
            raise AttributeError(*e.args)

    def __setattr__(self, key, value):
        if key == "_payment":
            return super().__setattr__(key, value)
        try:
            data = json.loads(self._payment.extra_data)
        except ValueError:
            data = {}
        data[key] = value
        self._payment.extra_data = json.dumps(data)


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
        _('payment provider'),
        help_text=_('Provider variant, that will be used for payment renewal'),
        max_length=255,
        default=None,
        null=True,
        blank=True,
    )

    class TimeUnit(enum.Enum):
        year = "year"
        month = "month"
        day = "day"

    def get_token(self) -> str:
        return self.token

    def set_recurrence(self, token: str, **kwargs):
        """
        Sets token and other values associated with subscription recurrence
        Kwargs can contain provider-specific values
        """
        self.token = token

    def get_period(self) -> int:
        raise NotImplementedError()

    def get_unit(self) -> TimeUnit:
        raise NotImplementedError()

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
    customer_ip_address = models.GenericIPAddressField(blank=True, null=True)
    extra_data = models.TextField(blank=True, default="")
    message = models.TextField(blank=True, default="")
    token = models.CharField(max_length=36, blank=True, default="")
    captured_amount = models.DecimalField(max_digits=9, decimal_places=2, default="0.0")

    class Meta:
        abstract = True

    def change_status(self, status: Union[PaymentStatus, str], message=""):
        """
        Updates the Payment status and sends the status_changed signal.
        """
        from .signals import status_changed

        self.status = status
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
        self.fraud_status = status
        self.fraud_message = message
        if commit:
            self.save()

    def save(self, **kwargs):
        if not self.token:
            tries = {}  # Stores a set of tried values
            while True:
                token = str(uuid4())
                if (
                    token in tries and len(tries) >= 100
                ):  # After 100 tries we are impliying an infinite loop
                    raise SystemExit("A possible infinite loop was detected")
                else:
                    if not self.__class__._default_manager.filter(token=token).exists():
                        self.token = token
                        break
                tries.add(token)

        return super().save(**kwargs)

    def __str__(self):
        return self.variant

    def get_form(self, data=None):
        provider = provider_factory(self.variant)
        return provider.get_form(self, data=data)

    def get_purchased_items(self) -> Iterable[PurchasedItem]:
        return []

    def get_failure_url(self) -> str:
        raise NotImplementedError()

    def get_success_url(self) -> str:
        raise NotImplementedError()

    def get_process_url(self) -> str:
        return reverse("process_payment", kwargs={"token": self.token})

    def get_payment_url(self) -> str:
        """
        Get the url the view that handles the payment (payment_details() in documentation)
        For now used only by PayU provider to redirect users back to CVV2 form
        """
        raise NotImplementedError()

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
        Used by providers, that use server initiated subscription workflow

        Throws RedirectNeeded if there is problem with the payment that needs to be solved by user
        """
        provider = provider_factory(self.variant)
        provider.autocomplete_with_subscription(self)

    def capture(self, amount=None):
        if self.status != PaymentStatus.PREAUTH:
            raise ValueError("Only pre-authorized payments can be captured.")
        provider = provider_factory(self.variant)
        amount = provider.capture(self, amount)
        if amount:
            self.captured_amount = amount
            self.change_status(PaymentStatus.CONFIRMED)

    def release(self):
        if self.status != PaymentStatus.PREAUTH:
            raise ValueError("Only pre-authorized payments can be released.")
        provider = provider_factory(self.variant)
        provider.release(self)
        self.change_status(PaymentStatus.REFUNDED)

    def refund(self, amount=None):
        if self.status != PaymentStatus.CONFIRMED:
            raise ValueError("Only charged payments can be refunded.")
        if amount:
            if amount > self.captured_amount:
                raise ValueError(
                    "Refund amount can not be greater then captured amount"
                )
            provider = provider_factory(self.variant)
            amount = provider.refund(self, amount)
            self.captured_amount -= amount
        if self.captured_amount == 0 and self.status != PaymentStatus.REFUNDED:
            self.change_status(PaymentStatus.REFUNDED)
        self.save()

    @property
    def attrs(self):
        return PaymentAttributeProxy(self)
