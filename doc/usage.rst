Making a payment
================

#. Create a :class:`Payment` instance::

      from decimal import Decimal

      from payments import get_payment_model
   
      Payment = get_payment_model()
      payment = Payment.objects.create(
          variant='default',  # this is the variant from PAYMENT_VARIANTS
          description='Book purchase',
          total=Decimal(120),
          tax=Decimal(20),
          currency='USD',
          delivery=Decimal(10),
          billing_first_name='Sherlock',
          billing_last_name='Holmes',
          billing_address_1='221B Baker Street',
          billing_address_2='',
          billing_city='London',
          billing_postcode='NW1 6XE',
          billing_country_code='UK',
          billing_country_area='Greater London')

#. Redirect the user to your payment handling view.
