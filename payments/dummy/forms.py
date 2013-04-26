from ..forms import PaymentForm
from ..models import PAYMENT_STATUS_CHOICES
from django import forms


class DummyForm(PaymentForm):

    status = forms.ChoiceField(choices=PAYMENT_STATUS_CHOICES)
