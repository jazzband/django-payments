Alternate provider_factory
==========================

You might want to be able to provide the ``PAYMENT_VARIANTS`` on a different fashion, such as per entity in your DB. 
Here's a quick exemple scenario, involving two DB entities for which provider settings has to be different:

Entity1 would have it's own PAYMENT_VARIANTS::

        PAYMENT_VARIANTS = {
            'stripe': ('payments.stripe.StripeProvider', {
                'secret_key': 'entity1secretkey',
                'public_key': 'entity1publickey'}),}

Entity2 also it's own, conflicting with Entity1::

        PAYMENT_VARIANTS = {
            'stripe': ('payments.stripe.StripeProvider', {
                'secret_key': 'entity2secretkey',
                'public_key': 'entity2publickey'}),}

How to solve this problem? We would be able to configure those values, per entity, through Django backend for exemple.


#. First define the alternate provider_factory method in the settings::

        PAYMENTS_ALTERNATE_PROVIDER_FACTORY = 'mypaymentapp.utils.alternate_payments_provider_factory'

#. Then define and code your alternate method logic::
        #mypaymentapp/utils.py
        def alternate_payments_provider_factory(variant):
            ...

