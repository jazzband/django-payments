import braintree
from django.core.exceptions import ImproperlyConfigured

from .forms import BraintreePaymentForm
from .. import PaymentStatus, RedirectNeeded
from ..core import BasicProvider


class BraintreeProvider(BasicProvider):
    """Payment provider for Braintree.

    This backend implements payments using `Braintree <https://www.braintreepayments.com/>`_.

    This backend does not support fraud detection.

    :param merchant_id: Merchant ID assigned by Braintree
    :param public_key: Public key assigned by Braintree
    :param private_key: Private key assigned by Braintree
    :param sandbox: Whether to use a sandbox environment for testing
    """

    def __init__(self, merchant_id, public_key, private_key, sandbox=True,
                 **kwargs):
        self.merchant_id = merchant_id
        self.public_key = public_key
        self.private_key = private_key

        environment = braintree.Environment.Sandbox
        if not sandbox:
            environment = braintree.Environment.Production

        braintree.Configuration.configure(
            environment, merchant_id=self.merchant_id,
            public_key=self.public_key, private_key=self.private_key)
        super().__init__(**kwargs)
        if not self._capture:
            raise ImproperlyConfigured(
                'Braintree does not support pre-authorization.')

    def get_form(self, payment, data=None):
        if payment.status == PaymentStatus.WAITING:
            payment.change_status(PaymentStatus.INPUT)
        form = BraintreePaymentForm(data=data, payment=payment, provider=self)
        if form.is_valid():
            form.save()
            raise RedirectNeeded(payment.get_success_url())
        return form
