"""Tests for webhook URL endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

from django.db.models import QuerySet
from django.http import HttpResponse
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


class ProcessDataLockingTestCase(TestCase):
    """Concurrent callbacks for one payment must be serialized."""

    @patch("payments.urls.provider_factory")
    @patch("payments.urls.get_payment_model")
    def test_process_data_locks_the_payment_row(self, mock_get_model, mock_factory):
        """The payment must be fetched with select_for_update().

        ``process_data`` already runs inside ``@atomic``, but it used to
        fetch the payment without a row lock. Two concurrent callbacks for
        the same payment - typically the provider's asynchronous webhook
        and the customer's browser POSTing to the same process URL - then
        interleave on instances loaded before each other's commit, and the
        loser overwrites the winner's state (observed in production as a
        captured, CONFIRMED payment being demoted to ERROR by a duplicate
        request holding a stale instance). Locking the row serializes the
        two handlers: the second one blocks until the first commits and
        sees the fresh state.
        """
        token = "550e8400-e29b-41d4-a716-446655440000"
        payment = Mock(variant="dummy")
        locked_queryset = MagicMock(spec=QuerySet)
        locked_queryset.get.return_value = payment
        payment_model = Mock()
        payment_model.objects.select_for_update.return_value = locked_queryset
        mock_get_model.return_value = payment_model
        provider = Mock()
        provider.process_data.return_value = HttpResponse("ok")
        mock_factory.return_value = provider

        response = self.client.post(f"/payments/process/{token}/")

        assert response.status_code == 200
        payment_model.objects.select_for_update.assert_called_once_with()
        locked_queryset.get.assert_called_once_with(token=uuid.UUID(token))
        provider.process_data.assert_called_once()
        assert provider.process_data.call_args[0][0] is payment
