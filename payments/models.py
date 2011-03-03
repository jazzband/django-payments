from django.db import models
from django.db.models import signals
from django.utils.translation import ugettext_lazy as _
from decimal import Decimal
from . import factory

PAYMENT_STATUS_CHOICES = (
    ('waiting', _(u'Waiting for confirmation')),
    ('confirmed', _(u'Confirmed')),
    ('rejected', _(u'Rejected')),
)
'''
List of possible payment statuses.
'''

class Payment(models.Model):
    '''
    Represents a single transaction. Each instance has one or more PaymentItem.
    '''
    variant = models.CharField(max_length=255)
    #: Transaction status
    status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='waiting')
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

    def get_form(self):
        '''
        Returns a form for this transaction.
        '''
        provider = factory(self.variant)
        return provider.get_form(self)

    def get_provider(self):
        '''
        Returns a provider assigned to given payment.
        '''
        provider = factory(self.variant)
        return provider

    def add_item(self, *args, **kwargs):
        '''
        Creates and returns a PaymentItem.

        All arguments are passed directly to PaymentItem constructor.
        '''
        return self.items.create(*args, **kwargs)

    def set_customer_detail(self, key, value):
        try:
            detail = self.customer_details.get(key=key)
        except CustomerDetail.DoesNotExist:
            detail = CustomerDetail(payment=self, key=key)
        detail.value = value
        detail.save()

    def get_customer_detail(self, key):
        try:
            return self.customer_details.get(key=key).value
        except CustomerDetail.DoesNotExist:
            return ''

    def change_status(self, status):
        '''
        Updates the Payment status and sends the status_changed signal.
        '''
        from signals import status_changed
        self.status = status
        self.save()
        status_changed.send(sender=type(self), instance=self)


class PaymentItem(models.Model):
    '''
    Represents a single item of a larger transaction (for example a single
    item in a shopping cart).
    
    Never create these objects directly, use Payment.add_item instead.
    '''
    payment = models.ForeignKey(Payment, related_name='items')
    name = models.CharField(max_length=100)
    quantity = models.DecimalField(max_digits=9, decimal_places=3, default='1')
    unit_price = models.DecimalField(max_digits=9, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)


class CustomerDetail(models.Model):
    payment = models.ForeignKey(Payment, related_name='customer_details')
    KEY_CHOICES = (
        ('first_name', _("First name")),
        ('last_name', _("Last name")),
        ('billing_address', _("Billing address")),
        ('billing_city', _("Billing city")),
        ('billing_postcode', _("Billing postal code")),
        ('billing_country_iso2', _("Billing country ISO 2-letter code")),
        ('shipping_address', _("Shipping address")),
        ('shipping_city', _("Shipping city")),
        ('shipping_postcode', _("Shipping postal code")),
        ('shipping_country_iso2', _("Shipping country ISO 2-letter code")),
        )
    key = models.CharField(max_length=50, choices=KEY_CHOICES)
    value = models.CharField(max_length=100)

    class Meta:
        unique_together = ('payment', 'key')

    def __unicode__(self):
        return u"%s: %s" % (self.key, self.value)


def _on_item_saved(sender, instance, created, **kwargs):
    '''
    Updates payment total
    '''
    payment = instance.payment
    total = Decimal(0)
    for elem in payment.items.all():
        total += elem.quantity * elem.unit_price
    payment.total = total
    payment.save()

signals.post_save.connect(_on_item_saved, sender=PaymentItem)

