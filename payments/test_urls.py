"""Tests for webhook URL endpoints."""

from __future__ import annotations

from unittest.mock import Mock
from unittest.mock import patch

from django.test import TestCase

from payments import PaymentError


class StaticCallbackTestCase(TestCase):
    """Test the static_callback webhook endpoint."""

    def test_invalid_provider_variant_returns_json_400(self):
        """Test that invalid provider variant returns JSON 400 with debug info."""
        response = self.client.post("/payments/process/invalid-variant/")

        assert response.status_code == 400
        assert response["Content-Type"] == "application/json"

        data = response.json()
        assert data["error"] == "Invalid payment provider"
        assert data["variant"] == "invalid-variant"

    @patch("payments.urls.provider_factory")
    def test_missing_token_returns_json_400(self, mock_factory):
        """Test that missing token returns JSON 400 with debug info."""
        mock_provider = Mock()
        mock_provider.get_token_from_request.return_value = None
        mock_factory.return_value = mock_provider

        response = self.client.post("/payments/process/dummy/")

        assert response.status_code == 400
        assert response["Content-Type"] == "application/json"

        data = response.json()
        assert data["error"] == "Could not extract payment token from webhook"
        assert data["variant"] == "dummy"

    @patch("payments.urls.provider_factory")
    def test_payment_error_includes_variant_and_code(self, mock_factory):
        """Test that PaymentError includes variant and error_code in response."""
        mock_provider = Mock()
        mock_provider.get_token_from_request.side_effect = PaymentError(
            code=400, message="Invalid signature"
        )
        mock_factory.return_value = mock_provider

        response = self.client.post("/payments/process/dummy/")

        assert response.status_code == 400
        assert response["Content-Type"] == "application/json"

        data = response.json()
        assert data["error"] == "Invalid signature"
        assert data["variant"] == "dummy"
        assert data["error_code"] == 400

    @patch("payments.urls.process_data")
    @patch("payments.urls.provider_factory")
    def test_payment_not_found_returns_json_404(self, mock_factory, mock_process):
        """Test that payment not found returns JSON 404 without token exposure."""
        from django.http import Http404

        mock_provider = Mock()
        mock_provider.get_token_from_request.return_value = (
            "550e8400-e29b-41d4-a716-446655440000"  # Realistic UUID token
        )
        mock_factory.return_value = mock_provider
        mock_process.side_effect = Http404("Payment not found")

        response = self.client.post("/payments/process/dummy/")

        assert response.status_code == 404
        assert response["Content-Type"] == "application/json"

        data = response.json()
        assert data["error"] == "Payment not found"
        assert data["variant"] == "dummy"
        # Token should not be exposed in error response for security
        assert "token" not in data
