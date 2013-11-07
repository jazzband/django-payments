import re

from django.template.loader import render_to_string
from django.forms.widgets import TextInput, MultiWidget


class CreditCardNumberWidget(TextInput):

    def render(self, name, value, attrs):
        if value:
            value = re.sub('[\s-]', '', value)
            value = ' '.join([value[i: i + 4]
                              for i in range(0, len(value), 4)])
        return super(CreditCardNumberWidget, self).render(name, value, attrs)


# Credit Card Expiry Fields from:
# http://www.djangosnippets.org/snippets/907/
class CreditCardExpiryWidget(MultiWidget):
    """MultiWidget for representing credit card expiry date."""
    def decompress(self, value):
        if value:
            return [value.month, value.year]
        else:
            return [None, None]

    def format_output(self, rendered_widgets):
        ctx = {'month': rendered_widgets[0], 'year': rendered_widgets[1]}
        return render_to_string('payments/credit_card_expiry_widget.html', ctx)
