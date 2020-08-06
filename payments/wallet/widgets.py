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
        try:  # Django < 2.2
            media._js = self.js
        except AttributeError:
            media._js_lists = [self.js]
        return media
