import re

from django.template.loader import render_to_string
from django.forms.widgets import TextInput, MultiWidget


class CreditCardNumberWidget(TextInput):

    def render(self, name, value, attrs=None):
        if value:
            value = re.sub('[\s-]', '', value)
            if len(value) == 16:
                value = ' '.join([value[0:4], value[4:8],
                                  value[8:12], value[12:16]])
            elif len(value) == 15:
                value = ' '.join([value[0:4], value[4:10], value[10:15]])
            elif len(value) == 14:
                value = ' '.join([value[0:4], value[4:10], value[10:14]])
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
