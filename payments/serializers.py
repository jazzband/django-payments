from __future__ import annotations

from rest_framework import serializers


class PaymentSerializer(serializers.Serializer):
    def validate(self, attrs):
        raise NotImplementedError

    def get_metadata(self):
        metadata = {}

        for field_name, field in self.fields.items():
            metadata[field_name] = {
                "required": field.required,
                "type": field.__class__.__name__,
                "choices": getattr(field, "choices", None),
            }
        return metadata
