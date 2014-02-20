from __future__ import unicode_literals
from django import forms

from ..forms import PaymentForm
from ..models import PAYMENT_STATUS_CHOICES


class DummyForm(PaymentForm):

    status = forms.ChoiceField(choices=PAYMENT_STATUS_CHOICES)
