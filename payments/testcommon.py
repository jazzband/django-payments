
from decimal import Decimal
from .models import BasePaymentLogic
from . import PaymentStatus, PurchasedItem
from .utils import getter_prefixed_address
from datetime import datetime
try:
    from unittest.mock import Mock
except ImportError:
    from mock import Mock

def create_test_payment(**_kwargs):
    class TestPayment(Mock, BasePaymentLogic):
        id = 523
        pk = id
        description = 'payment'
        currency = 'USD'
        delivery = Decimal(10.8)
        status = PaymentStatus.WAITING
        message = ""
        tax = Decimal(10)
        token = "354338723"
        total = Decimal(100)
        captured_amount = Decimal("0.0")
        extra_data = ""
        variant = "undefined"
        transaction_id = None
        created = datetime.now()
        modified = datetime.now()

        billing_first_name = 'John'
        billing_last_name = 'Smith'
        billing_address_1 = 'JohnStreet 23'
        billing_address_2 = ''
        billing_city = 'Neches'
        billing_postcode = "75779"
        billing_country_code = "US"
        billing_country_area = "Tennessee"
        billing_email = "example@example.com"
        customer_ip_address = "192.78.6.6"

        get_billing_address = getter_prefixed_address("billing")
        get_shipping_address = get_billing_address

        def capture(self, amount=None):
            amount = amount or self.total
            self.captured_amount = amount
            self.change_status(PaymentStatus.CONFIRMED)

        def change_status(self, status, message=''):
            '''
            Updates the Payment status and sends the status_changed signal.
            '''
            self.status = status
            self.message = message

        def get_purchased_items(self):
            return [
                PurchasedItem(
                    name='foo', quantity=10, price=Decimal('20'),
                    currency='USD', sku='bar')]

        def get_failure_url(self):
            return 'http://cancel.com'

        def get_process_url(self):
            return 'http://example.com'

        def get_success_url(self):
            return 'http://success.com'

        def save(self):
            return self
    # workaround limitation in python
    for key, val in _kwargs.items():
        setattr(TestPayment, key, val)
    return TestPayment
