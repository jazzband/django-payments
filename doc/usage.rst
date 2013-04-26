================
Making a payment
================

#. Call :meth:`factory` to obtain a provider instance

   .. code-block:: python

      from payments import factory

      provider = factory('somevariant')

#. Call :meth:`BasicProvider.create_payment` on the provider to obtain a form

   .. code-block:: python

      payment = provider.create_payment(currency='USD')

#. Fill the payment object with useful data

   .. code-block:: python

      payment.add_item(name='Some item', unit_price='5.00', tax_rate='2.00')

#. Pass the form to the template of your choice

   .. code-block:: python

      form = payment.get_form()

#. Display the form using its *action* and *method*

   .. code-block:: html

      <form action="{{ form.action }}" method="{{ form.method }}">
          {{ form.as_p }}
          <p><input type="submit" value="Proceed" /></p>
      </form>
