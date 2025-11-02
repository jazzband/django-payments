from __future__ import annotations

from payments.dummy.serializers import DummySerializer


def test_serializer_get_metadata_returns_correct_structure():
    metadata = DummySerializer().get_metadata()
    # Fields that should exist
    expected_fields = {
        "status",
        "fraud_status",
        "gateway_response",
        "verification_result",
    }
    assert expected_fields.issubset(set(metadata.keys()))
    # For each, check required, type, choices keys
    for _, meta in metadata.items():
        assert "required" in meta
        assert "type" in meta
        assert "choices" in meta


def test_serializer_validation_success():
    data = {
        "status": "waiting",
        "fraud_status": "unknown",
        "gateway_response": "3ds-disabled",
    }
    serializer = DummySerializer(data=data)
    serializer.is_valid()
    assert not serializer.errors


def test_serializer_validation_failed():
    data = {
        "status": "waiting",
        "fraud_status": "unknown",
        "gateway_response": "validation-failure",
        "verification_result": "confirmed",
    }
    serializer = DummySerializer(data=data)
    serializer.is_valid()
    assert serializer.errors
