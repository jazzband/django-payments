from __future__ import unicode_literals

from django.forms.widgets import HiddenInput


class WalletWidget(HiddenInput):

    def __init__(self, provider, payment, *args, **kwargs):

        kwargs['attrs'] = {
            'id': 'google-wallet-id',
            'data-jwt': provider.get_jwt_data(payment),
            'data-success-url': payment.get_success_url(),
            'data-failure-url': payment.get_failure_url(),
        }
        super(WalletWidget, self).__init__(*args, **kwargs)
        self.js = [provider.library, 'js/payments/wallet.js']

    @property
    def media(self):
        media = super(WalletWidget, self).media
        media._js = self.js
        return media
