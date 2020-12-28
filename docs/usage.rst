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
          billing_country_area='Greater London',
          customer_ip_address='127.0.0.1')

#. Redirect the user to your payment handling view.


Payment amounts
---------------
The :class:`Payment` instance provides two fields that let you check the total charged amount and the amount actually captured::

      >>> payment.total
      Decimal('181.38')

      >>> payment.captured_amount
      Decimal('0')


Payment statuses
----------------
A payment may have one of several statuses, that indicates its current state. The status is stored in ``status`` field of your :class:`Payment` instance. Possible statuses are:

``waiting``
      Payment is waiting for confirmation. This is the first status, which is assigned to the payment after creating it.

``input``
      Customer requested the payment form and is providing the payment data.

``preauth``
      Customer has authorized the payment and now it can be captured. Please remember, that this status is only possible when the ``capture`` flag is set to ``False`` (see :ref:`capture-payments` for details).

``confirmed``
      Payment has been finalized or the the funds were captured (when using ``capture=False``).

``rejected``
      The payment was rejected by the payment gateway. Inspect the contents of the ``payment.message`` and ``payment.extra_data`` fields to see the gateway response.

``refunded``
      Payment has been successfully refunded to the customer (see :ref:`refunding` for details).

``error``
      An error occurred during the communication with the payment gateway. Inspect the contents of the ``payment.message`` and ``payment.extra_data`` fields to see the gateway response.



Fraud statuses
--------------

Some gateways provide services used for fraud detection. You can check the fraud status of your payment by accessing ``payment.fraud_status`` and ``payment.fraud_message`` fields. The possible fraud statuses are:

``unknown``
      The fraud status is unknown. This is the default status for gateways, that do not involve fraud detection.

``accept``
      Fraud was not detected.

``reject``
      Fraud service detected some problems with the payment. Inspect the details by accessing the ``payment.fraud_message`` field.

``review``
      The payment was marked for review.
