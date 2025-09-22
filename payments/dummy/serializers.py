from __future__ import annotations

from rest_framework import serializers

from payments import FraudStatus
from payments import PaymentStatus
from payments.serializers import PaymentSerializer

RESPONSE_CHOICES = (
    ("3ds-disabled", "3DS disabled"),
    ("validation-failure", "3DS disabled"),
    ("failure", "Gateway connection error"),
    ("payment-error", "Gateway returned unsupported response"),
)


class DummySerializer(PaymentSerializer):
    status = serializers.ChoiceField(choices=PaymentStatus.CHOICES)
    fraud_status = serializers.ChoiceField(choices=FraudStatus.CHOICES)
    gateway_response = serializers.ChoiceField(choices=RESPONSE_CHOICES)
    verification_result = serializers.ChoiceField(
        choices=PaymentStatus.CHOICES, required=False
    )

    def validate(self, data):
        if data.get("gateway_response") == "validation-failure":
            raise serializers.ValidationError(
                "Provided data is not valid, please try again with correct data"
            )
        return data
