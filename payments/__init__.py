from collections import namedtuple

PurchasedItem = namedtuple('PurchasedItem',
                           'name, quantity, price, currency, sku')


class RedirectNeeded(Exception):
    pass


class PaymentError(Exception):
    pass


class ExternalPostNeeded(Exception):
    pass
