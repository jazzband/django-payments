from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from payments.fields import CreditCardNumberField


def test_validate_rejects_card_type_not_in_valid_types() -> None:
    # 4111111111111111 is a valid Visa test number (passes Luhn check)
    field = CreditCardNumberField(valid_types=["mastercard"])
    with pytest.raises(ValidationError, match="We accept only MasterCard"):
        field.validate("4111111111111111")
