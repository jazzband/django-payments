"""Tests for webhook URL endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from django.db.models import QuerySet
from django.http import Http404
from django.http import HttpResponse
from django.test import TestCase

from payments import PaymentError
from payments.urls import get_payment_or_404
from payments.urls import process_data
from payments.urls import process_payment_data


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
        payment_model._default_manager.select_for_update.return_value = locked_queryset
        mock_get_model.return_value = payment_model
        provider = Mock()
        provider.process_data.return_value = HttpResponse("ok")
        mock_factory.return_value = provider

        response = self.client.post(f"/payments/process/{token}/")

        assert response.status_code == 200
        payment_model._default_manager.select_for_update.assert_called_once_with()
        locked_queryset.get.assert_called_once_with(token=uuid.UUID(token))
        provider.process_data.assert_called_once()
        assert provider.process_data.call_args[0][0] is payment


class MultiplePaymentModelsTestCase(TestCase):
    """The callback flow must be reusable for secondary payment models.

    ``PAYMENT_MODEL`` names a single model, so a project that also charges
    e.g. subscriptions or marketplace orders through their own payment
    models has to reimplement this view. Copies drift: they miss fixes
    made here later (the row locking above is a real example - copies that
    predate it stayed vulnerable). Exposing the two steps and letting the
    view take an explicit model keeps such projects on this code path.
    """

    @staticmethod
    def _locked_model(payment):
        locked_queryset = MagicMock(spec=QuerySet)
        locked_queryset.get.return_value = payment
        payment_model = Mock()
        payment_model._default_manager.select_for_update.return_value = locked_queryset
        return payment_model, locked_queryset

    @patch("payments.urls.get_payment_model")
    def test_get_payment_or_404_locks_the_default_model(self, mock_get_model):
        """Without an explicit model the configured one is used, locked."""
        payment = Mock(variant="dummy")
        payment_model, locked_queryset = self._locked_model(payment)
        mock_get_model.return_value = payment_model
        token = "550e8400-e29b-41d4-a716-446655440000"

        assert get_payment_or_404(token) is payment

        payment_model._default_manager.select_for_update.assert_called_once_with()
        locked_queryset.get.assert_called_once_with(token=token)

    @patch("payments.urls.get_payment_model")
    def test_get_payment_or_404_locks_an_explicit_model(self, mock_get_model):
        """An explicit model is used instead of the configured one."""
        payment = Mock(variant="dummy")
        payment_model, locked_queryset = self._locked_model(payment)
        token = "550e8400-e29b-41d4-a716-446655440000"

        assert get_payment_or_404(token, payment_model=payment_model) is payment

        mock_get_model.assert_not_called()
        payment_model._default_manager.select_for_update.assert_called_once_with()
        locked_queryset.get.assert_called_once_with(token=token)

    @patch("payments.urls.provider_factory")
    def test_process_payment_data_resolves_the_provider(self, mock_factory):
        """Without an explicit provider one is built from the variant."""
        payment = Mock(variant="dummy")
        provider = Mock()
        provider.process_data.return_value = HttpResponse("ok")
        mock_factory.return_value = provider
        request = Mock()

        response = process_payment_data(payment, request)

        assert response.status_code == 200
        mock_factory.assert_called_once_with("dummy", payment)
        provider.process_data.assert_called_once_with(payment, request)

    @patch("payments.urls.provider_factory")
    def test_process_payment_data_raises_404_for_unknown_variant(self, mock_factory):
        """An unconfigured variant is a 404, as in the view."""
        mock_factory.side_effect = ValueError("no such variant")

        with pytest.raises(Http404):
            process_payment_data(Mock(variant="nope"), Mock())

    @patch("payments.urls.provider_factory")
    def test_process_payment_data_uses_the_given_provider(self, mock_factory):
        """An explicit provider skips the factory (static_callback path)."""
        payment = Mock(variant="dummy")
        provider = Mock()
        provider.process_data.return_value = HttpResponse("ok")

        process_payment_data(payment, Mock(), provider=provider)

        mock_factory.assert_not_called()
        provider.process_data.assert_called_once()

    @patch("payments.urls.provider_factory")
    @patch("payments.urls.get_payment_model")
    def test_process_data_accepts_an_explicit_payment_model(
        self, mock_get_model, mock_factory
    ):
        """The view can be routed for a secondary payment model.

        Projects can wire ``process_data`` in their own URLconf with a
        ``payment_model`` kwarg instead of copying the whole view.
        """
        payment = Mock(variant="dummy")
        payment_model, locked_queryset = self._locked_model(payment)
        provider = Mock()
        provider.process_data.return_value = HttpResponse("ok")
        mock_factory.return_value = provider
        token = "550e8400-e29b-41d4-a716-446655440000"

        response = process_data(Mock(), token, payment_model=payment_model)

        assert response.status_code == 200
        mock_get_model.assert_not_called()
        payment_model._default_manager.select_for_update.assert_called_once_with()
        locked_queryset.get.assert_called_once_with(token=token)
        assert provider.process_data.call_args[0][0] is payment
