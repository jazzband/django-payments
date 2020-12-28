from django import forms

from .. import FraudStatus
from .. import PaymentStatus
from ..forms import PaymentForm


class DummyForm(PaymentForm):
    RESPONSE_CHOICES = (
        ('3ds-disabled', '3DS disabled'),
        ('3ds-redirect', '3DS redirect'),
        ('failure', 'Gateway connection error'),
        ('payment-error', 'Gateway returned unsupported response')
    )
    status = forms.ChoiceField(choices=PaymentStatus.CHOICES)
    fraud_status = forms.ChoiceField(choices=FraudStatus.CHOICES)
    gateway_response = forms.ChoiceField(choices=RESPONSE_CHOICES)
    verification_result = forms.ChoiceField(choices=PaymentStatus.CHOICES,
                                            required=False)

    def clean(self):
        cleaned_data = super().clean()
        gateway_response = cleaned_data.get('gateway_response')
        verification_result = cleaned_data.get('verification_result')
        if gateway_response == '3ds-redirect' and not verification_result:
            raise forms.ValidationError(
                'When 3DS is enabled you must set post validation status')
        return cleaned_data
