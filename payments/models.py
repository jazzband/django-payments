import json
from typing import Iterable
from uuid import uuid4
import logging

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from . import FraudStatus, PaymentStatus, PurchasedItem
from .core import provider_factory

# Get an instance of a logger
logger = logging.getLogger(__name__)

class PaymentAttributeProxy:

    def __init__(self, payment):
        self._payment = payment
        super().__init__()

    def __getattr__(self, item):
        data = json.loads(self._payment.extra_data or '{}')
        try:
            return data[item]
        except KeyError as e:
            raise AttributeError(*e.args)

    def __setattr__(self, key, value):
        if key == '_payment':
            return super().__setattr__(key, value)
        try:
            data = json.loads(self._payment.extra_data)
        except ValueError:
            data = {}
        data[key] = value
        self._payment.extra_data = json.dumps(data)


class BasePayment(models.Model):
    '''
    Represents a single transaction. Each instance has one or more PaymentItem.
    '''
    variant = models.CharField(max_length=255)
    #: Transaction status
    status = models.CharField(
        max_length=10, choices=PaymentStatus.CHOICES,
        default=PaymentStatus.WAITING)
    fraud_status = models.CharField(
        _('fraud check'), max_length=10, choices=FraudStatus.CHOICES,
        default=FraudStatus.UNKNOWN)
    fraud_message = models.TextField(blank=True, default='')
    #: Creation date and time
    created = models.DateTimeField(auto_now_add=True)
    #: Date and time of last modification
    modified = models.DateTimeField(auto_now=True)
    #: Transaction ID (if applicable)
    transaction_id = models.CharField(max_length=255, blank=True)
    #: Currency code (may be provider-specific)
    currency = models.CharField(max_length=10)
    #: Total amount (gross)
    total = models.DecimalField(max_digits=9, decimal_places=2, default='0.0')
    delivery = models.DecimalField(
        max_digits=9, decimal_places=2, default='0.0')
    tax = models.DecimalField(max_digits=9, decimal_places=2, default='0.0')
    description = models.TextField(blank=True, default='')
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
    extra_data = models.TextField(blank=True, default='')
    message = models.TextField(blank=True, default='')
    token = models.CharField(max_length=36, blank=True, default='')
    captured_amount = models.DecimalField(
        max_digits=9, decimal_places=2, default='0.0')

    class Meta:
        abstract = True

    def change_status(self, status: PaymentStatus, message=''):
        '''
        Updates the Payment status and sends the status_changed signal.
        '''
        if  self.status != status:
            from .signals import status_changed
            self.status = status
            self.message = message
            self.save()
            for receiver, result in status_changed.send_robust(sender=type(self), instance=self):
                if isinstance(result, Exception):
                    logger.critical(result)
        else:
            self.save()

    def change_fraud_status(self, status: PaymentStatus, message='', commit=True):
        available_statuses = [choice[0] for choice in FraudStatus.CHOICES]
        if status not in available_statuses:
            raise ValueError(
                'Wrong status "{}", it should be one of: {}'.format(
                    status, ', '.join(available_statuses)))
        self.fraud_status = status
        self.fraud_message = message
        if commit:
            self.save()

    def save(self, **kwargs):
        if not self.token:
            tries = {}  # Stores a set of tried values
            while True:
                token = str(uuid4())
                if token in tries and len(tries) >= 100:  # After 100 tries we are impliying an infinite loop
                    raise SystemExit('A possible infinite loop was detected')
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
        return reverse('process_payment', kwargs={'token': self.token})

    def capture(self, amount=None, final=True):
        ''' Capture a fraction of the total amount of a payment. Return amount captured or None '''
        if self.status != PaymentStatus.PREAUTH:
            raise ValueError(
                'Only pre-authorized payments can be captured.')
        provider = provider_factory(self.variant)
        amount = provider.capture(self, amount, final)
        if amount:
            self.captured_amount += amount
            if final:
                self.change_status(PaymentStatus.CONFIRMED)
        return amount

    def release(self):
        ''' Annilates captured payment '''
        if self.status != PaymentStatus.PREAUTH:
            raise ValueError(
                'Only pre-authorized payments can be released.')
        provider = provider_factory(self.variant)
        provider.release(self)
        self.change_status(PaymentStatus.REFUNDED)

    def refund(self, amount=None):
        ''' Refund payment, return amount which was refunded or None '''
        if self.status != PaymentStatus.CONFIRMED:
            raise ValueError(
                'Only charged payments can be refunded.')
        if amount:
            if amount > self.captured_amount:
                raise ValueError(
                    'Refund amount can not be greater then captured amount')
        provider = provider_factory(self.variant)
        amount = provider.refund(self, amount)
        if amount:
            self.captured_amount -= amount
            if self.captured_amount == 0 and self.status != PaymentStatus.REFUNDED:
                self.change_status(PaymentStatus.REFUNDED)
            self.save()
        return amount

    @property
    def attrs(self):
        return PaymentAttributeProxy(self)
