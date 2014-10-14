Making a payment
================

The flow of making a payment may vary, depending on the kind and complexity of your application, but in general, it consists of a few typical steps:

  * first of all, you may want to give your users a choice of payment method, as there is a number of payment gateways
  * when the user chooses his method, you should display a form, that will handle user's input (such as a credit card number) or redirect him directly to the payment gateway, that will handle this
  * based on the result of communication with payment gateway, you should inform the users about the success or failure of the payment

In this section we describe, how to implement a example payment flow using ``django-payments``. In addition, we explain some of the useful attributes of a :class:`Payment` instance and its statuses.  


Integrating ``django-payments``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Let's assume that we have an e-commerce application, where users can place some orders.

#. Create a form, that will allow choosing the payment variant and render it in a view, that will redirect to the payment::
    
    # forms.py
    from django import forms

    PAYMENT_CHOICES = [
        ('default', 'Dummy provider'),
    ]

    class PaymentMethodsForm(forms.Form):
        method = forms.ChoiceField(choices=PAYMENT_CHOICES)


    # views.py
    from django.shortcuts import redirect, render_to_response
    from models import Order

    def order_details(request, pk):
        order = Order.object.get(pk=pk)
        form = PaymentMethodsForm(request.POST or None)
        if form.is_valid():
            payment_method = form.cleaned_data['method']
            return redirect('app:payment',
                            order_pk=order.pk,
                            variant=payment_method)
        else:
            return render_to_response('order/details.html',
                                      {'order': order, 'form': form})


#. Create a view, that will handle creating a new :class:`Payment` instance::

      # views.py
      from decimal import Decimal
      from django.shortcuts import redirect, render_to_response
      from payments import get_payment_model, RedirectNeeded

      def make_payment(request, order_pk, variant):
          Payment = get_payment_model()
          payment = Payment.objects.create(
              variant=variant,
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

          try:
              form = payment.get_form(data=request.POST or None)
          except RedirectNeeded as redirect_to:
              return redirect(str(redirect_to))
          except Exception:
              payment.change_status('error')
              return redirect('order:details', pk=order.pk)

          template = 'order/payment/%s.html' % variant
          return render_to_response(request, template,
                                    {'form': form, 'payment': payment})



Useful payment attributes
^^^^^^^^^^^^^^^^^^^^^^^^^
Below we present some of the useful attributes that are provided by the :class:`Payment` instances.


Amounts
-------
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
