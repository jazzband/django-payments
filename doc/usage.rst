Making a payment
================

The flow of making a payment may vary, depending on the kind and complexity of a application. Using ``django-payments`` it would consist of the following steps:

  * User picks a payment method. Based on the choice, you create a payment object.
  * The object provides you a payment form responsible for taking user's input or for submitting necessary information to a third party gateway. The experience depends on a particular payment backend.
  * This can result in the payment completing immediately or the user leaving the current page and being redirected to either an external or local page where further interaction may happen (such as PayPal login or 3-D Secure credit card validation).
  * Once the process is complete, the payment status changes and a signal is dispatched. The user is finally redirected to either the success or failure URL provided by the payment object.


Below we show how to implement the above presented flow.


#. Make sure you have set up ``django-payments`` properly, according to the guidelines showed in the :ref:`how-to-install` section. 

#. Create a form that will allow choosing the payment variant and a view to render it. Ensure, that the choices defined in ``PAYMENT_CHOICES`` correspond to ``PAYMENT_VARIANTS`` defined in your ``settings.py`` (see :ref:`how-to-install`). If your application does not support multiple payment variants, this step may be omitted::
    
      # mypaymentapp/forms.py
      from django import forms


      PAYMENT_CHOICES = [
          ('default', 'Dummy provider'),
      ]

      class PaymentMethodsForm(forms.Form):
          method = forms.ChoiceField(choices=PAYMENT_CHOICES)


      # mypaymentapp/views.py
      from django.shortcuts import redirect
      from django.template.response import TemplateResponse

      from mypaymentapp.forms import PaymentMethodsForm


      def payment_method(request):
          form = PaymentMethodsForm(request.POST or None)
          if form.is_valid():
              payment_method = form.cleaned_data['method']
              return redirect('payment-details', variant=payment_method)
          else:
              return TemplateResponse(request, 'payment_method.html',
                                      {'form': form})


#. Write a view in which a new :class:`Payment` instance will be created based on the chosen payment variant. It should be populated with the corresponding payment data, such as total amount, currency and buyer's address. The following view is also responsible for rendering a payment form provided by the :class:`Payment` instance. Note, that the form may throw a `RedirectNeeded` exception, which will provide a redirect URL you should use. When the payment process is completed, user will be automatically redirected to either success or failure URL::

      # mypaymentapp/views.py
      from decimal import Decimal

      from django.shortcuts import redirect
      from django.template.response import TemplateResponse
      from payments import get_payment_model, RedirectNeeded


      def payment_details(request, variant):
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
          return TemplateResponse(request, 'payment.html',
                                  {'form': form, 'payment': payment})


#. Prepare a template that displays the form using its *action* and *method*:

   .. code-block:: html

      <!-- templates/payment.html -->
      <form action="{{ form.action }}" method="{{ form.method }}">
          {{ form.as_p }}
          <p><input type="submit" value="Proceed" /></p>
      </form>


Payment attributes
^^^^^^^^^^^^^^^^^^
The :class:`Payment` instance provides fields that let you check the total charged amount and the amount actually captured::

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
