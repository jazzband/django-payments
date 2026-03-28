from __future__ import annotations

import re
from typing import TYPE_CHECKING
from typing import Any

from django.forms.widgets import MultiWidget
from django.forms.widgets import Select
from django.forms.widgets import TextInput

if TYPE_CHECKING:
    from datetime import date

    from django.forms.renderers import BaseRenderer
    from django.utils.safestring import SafeString


class CreditCardNumberWidget(TextInput):
    def render(
        self,
        name: str,
        value: str | None,
        attrs: dict[str, Any] | None = None,
        renderer: BaseRenderer | None = None,
    ) -> SafeString:
        if value:
            value = re.sub(r"[\s-]", "", value)
            if len(value) == 16:
                value = " ".join([value[0:4], value[4:8], value[8:12], value[12:16]])
            elif len(value) == 15:
                value = " ".join([value[0:4], value[4:10], value[10:15]])
            elif len(value) == 14:
                value = " ".join([value[0:4], value[4:10], value[10:14]])
        return super().render(name, value, attrs)


# Credit Card Expiry Fields from:
# http://www.djangosnippets.org/snippets/907/
class CreditCardExpiryWidget(MultiWidget):
    """MultiWidget for representing credit card expiry date."""

    template_name = "payments/credit_card_expiry_widget.html"

    def decompress(self, value: date | None) -> list[int | None]:
        if value:
            return [value.month, value.year]
        return [None, None]


class SensitiveTextInput(TextInput):
    template_name = "payments/sensitive_text_input.html"


class SensitiveSelect(Select):
    template_name = "payments/sensitive_select.html"
