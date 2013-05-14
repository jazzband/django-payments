import re

from django.forms.widgets import TextInput, HiddenInput


class CreditCardNumberWidget(TextInput):

    def render(self, name, value, attrs):
        if value:
            value = re.sub('[\s-]', '', value)
            value = ' '.join([value[i: i + 4]
                              for i in xrange(0, len(value), 4)])
        return super(CreditCardNumberWidget, self).render(name, value, attrs)


class WalletWidget(HiddenInput):

    def __init__(self, provider, *args, **kwargs):

        kwargs['attrs'] = {
            'id': 'google-wallet-id',
            'data-jwt': provider.get_jwt_data(),
        }
        super(WalletWidget, self).__init__(*args, **kwargs)
        self.js = [provider.library, 'payments/js/wallet.js']

    @property
    def media(self):
        media = super(WalletWidget, self).media
        media._js = self.js
        return media
