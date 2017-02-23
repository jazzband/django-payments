import re

from django import VERSION as DJANGO_VERSION
from django.forms.utils import flatatt
from django.forms.widgets import TextInput, MultiWidget, Select
from django.template.loader import render_to_string
from django.utils.encoding import force_text
from django.utils.html import format_html
from django.utils.safestring import mark_safe


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


class SensitiveTextInput(TextInput):

    def render(self, name, value, attrs=None):
        # Explicitly skip parent implementation and exclude
        # 'name' from attrs
        if value is None:
            value = ''
        final_attrs = self.build_attrs(attrs, type=self.input_type)
        if value != '':
            # Only add the 'value' attribute if a value is non-empty.
            final_attrs['value'] = force_text(self.format_value(value))
        return format_html('<input{} />', flatatt(final_attrs))


class SensitiveSelect(Select):

    def render(self, name, value, attrs=None):
        if value is None:
            value = ''
        final_attrs = self.build_attrs(attrs)
        output = [format_html('<select{}>', flatatt(final_attrs))]
        if DJANGO_VERSION <= (1, 10, 0):
            options = self.render_options([], [value])
        else:
            options = self.render_options([value])
        if options:
            output.append(options)
        output.append('</select>')
        return mark_safe('\n'.join(output))
