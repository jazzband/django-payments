from django.core.urlresolvers import reverse

PAYMENT_VARIANTS = {
    'default': ('payments.dummy.DummyProvider', {
            'url': 'http://google.pl/',
        },
    ),
}

class BasicProvider(object):
    '''
    This class defines the provider API. It should not be instantiated
    directly. Use factory instead.
    '''
    _method = 'post'

    def _action(self):
        return reverse('process_payment', args=[self._variant])
    _action = property(_action)

    def __init__(self, variant):
        self._variant = variant

    def create_payment(self, commit=True, *args, **kwargs):
        '''
        Creates a new payment. Always use this method instead of manually
        creating a Payment instance directly.
        
        All arguments are passed directly to Payment constructor.
        
        When implementing a new payment provider, you may overload this method
        to return a specialized version of Payment instead.
        '''
        from models import Payment
        payment = Payment(variant=self._variant, *args, **kwargs)
        if commit:
            payment.save()
        return payment

    def get_hidden_fields(self, payment):
        '''
        Converts a payment into a dict containing transaction data. Use
        get_form instead to get a form suitable for templates.
        
        When implementing a new payment provider, overload this method to
        transfer provider-specific data.
        '''
        raise NotImplementedError

    def get_form(self, payment):
        '''
        Converts *payment* into a form suitable for Django templates.
        '''
        from forms import PaymentForm
        return PaymentForm(self.get_hidden_fields(payment), self._action, self._method)

    def process_data(self, request):
        '''
        Process callback request from a payment provider.
        '''
        raise NotImplementedError

def factory(variant='default'):
    '''
    Takes the optional *variant* name and returns an appropriate implementation.
    '''
    from django.conf import settings
    variants = getattr(settings, 'PAYMENT_VARIANTS', PAYMENT_VARIANTS)
    handler, config = variants.get(variant, (None, None))
    if not handler:
        raise ValueError('Payment variant does not exist: %s' % variant)
    path = handler.split('.')
    if len(path) < 2:
        raise ValueError('Payment variant uses an invalid payment module: %s' % variant)
    module_path = '.'.join(path[:-1])
    klass_name = path[-1]
    module = __import__(module_path, globals(), locals(), [klass_name])
    klass = getattr(module, klass_name)
    return klass(variant=variant, **config)

