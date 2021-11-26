from django import forms

from payments import get_payment_model


class TestPaymentForm(forms.ModelForm):
    class Meta:
        model = get_payment_model()
        fields = ["variant", "currency", "total"]
