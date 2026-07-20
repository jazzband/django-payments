"""Unit tests for the PayPal PPCP provider (Orders v2 + Vault).

HTTP layer is mocked; the payment object is a stub mirroring the
django-payments BasePayment surface the provider touches, following the
style of the provider tests in django-payments itself.
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests
from django.test import RequestFactory
from django.test import TestCase
from django.test import override_settings

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded

from .ppcp import PaypalPPCPProvider

ORDER_ID = "5O190127TN364715T"
CAPTURE_ID = "3C679366HH908993F"
VAULT_ID = "8kk8451t"

OAUTH_RESPONSE = {
    "token_type": "Bearer",
    "access_token": "A21AAFs",
    "expires_in": 32400,
}

CREATE_ORDER_RESPONSE = {
    "id": ORDER_ID,
    "status": "PAYER_ACTION_REQUIRED",
    "links": [
        {
            "href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/" + ORDER_ID,
            "rel": "self",
            "method": "GET",
        },
        {
            "href": "https://www.sandbox.paypal.com/checkoutnow?token=" + ORDER_ID,
            "rel": "payer-action",
            "method": "GET",
        },
    ],
}


def capture_response(status="COMPLETED", vault=None, fee="0.84"):
    response = {
        "id": ORDER_ID,
        "status": status,
        "purchase_units": [
            {
                "payments": {
                    "captures": [
                        {
                            "id": CAPTURE_ID,
                            "status": "COMPLETED",
                            "amount": {"currency_code": "USD", "value": "14.31"},
                            "seller_receivable_breakdown": {
                                "paypal_fee": {
                                    "currency_code": "USD",
                                    "value": fee,
                                },
                            },
                        }
                    ]
                }
            }
        ],
    }
    if vault:
        response["payment_source"] = {
            "paypal": {"attributes": {"vault": {"id": vault, "status": "VAULTED"}}}
        }
    return response


PERSISTED_FIELDS = (
    "status",
    "message",
    "transaction_id",
    "captured_amount",
    "extra_data",
)


class PaymentStub:
    """Stub of the django-payments BasePayment surface used by the provider.

    ``save``/``change_status`` mimic BasePayment's persistence semantics --
    ``change_status`` saves with ``update_fields=["status", "message"]``, so
    any other field the provider assigned but did not save explicitly is
    LOST. ``persisted`` holds what would have reached the database.
    """

    def __init__(self):
        self.id = 42
        self.pk = 42
        self.token = "payment-token-uuid"
        self.status = PaymentStatus.WAITING
        self.message = ""
        self.currency = "USD"
        self.total = Decimal("14.31")
        self.captured_amount = Decimal("0")
        self.transaction_id = ""
        self.description = "Plan purchase"
        self.extra_data = ""
        self.renew_token_calls = []
        self.renew_token = None
        self.persisted = {}
        self.saved = False

    def save(self, update_fields=None):
        self.saved = True
        fields = update_fields if update_fields is not None else PERSISTED_FIELDS
        for field in fields:
            self.persisted[field] = getattr(self, field)

    def change_status(self, status, message=""):
        # Mirrors BasePayment.change_status: partial save on purpose.
        self.status = status
        self.message = message
        self.save(update_fields=["status", "message"])

    def get_process_url(self):
        return f"/payments/process/{self.token}/"

    def get_success_url(self):
        return "/payment/success/"

    def get_failure_url(self):
        return "/payment/failure/"

    def get_renew_token(self):
        return self.renew_token

    def set_renew_token(self, token, **kwargs):
        self.renew_token_calls.append((token, kwargs))


@override_settings(PAYMENT_HOST="example.com")
class PaypalPPCPProviderTests(TestCase):
    def setUp(self):
        self.provider = PaypalPPCPProvider(
            client_id="client-id",
            secret="secret",
            endpoint="https://api-m.sandbox.paypal.com",
        )
        self.vault_provider = PaypalPPCPProvider(
            client_id="client-id",
            secret="secret",
            endpoint="https://api-m.sandbox.paypal.com",
            vault=True,
        )
        self.payment = PaymentStub()
        self.factory = RequestFactory()

    def _mock_api(self, provider, responses):
        """Patch OAuth + api_post; api_post returns responses in order."""
        provider.get_access_token = MagicMock(return_value="Bearer A21AAFs")
        mock = MagicMock(side_effect=responses)
        provider.api_post = mock
        return mock

    def test_get_form_creates_order_and_redirects(self):
        api = self._mock_api(self.provider, [CREATE_ORDER_RESPONSE])
        with pytest.raises(RedirectNeeded) as cm:
            self.provider.get_form(self.payment)
        assert (
            str(cm.value)
            == "https://www.sandbox.paypal.com/checkoutnow?token=" + ORDER_ID
        )
        assert self.payment.status == PaymentStatus.WAITING
        assert json.loads(self.payment.extra_data)["ppcp_order"]["id"] == ORDER_ID
        body = api.call_args_list[0].args[1]
        assert body["intent"] == "CAPTURE"
        assert body["purchase_units"][0]["amount"] == {
            "currency_code": "USD",
            "value": "14.31",
        }
        assert "attributes" not in body["payment_source"]["paypal"]

    def test_get_form_vault_variant_requests_vaulting(self):
        api = self._mock_api(self.vault_provider, [CREATE_ORDER_RESPONSE])
        with pytest.raises(RedirectNeeded):
            self.vault_provider.get_form(self.payment)
        body = api.call_args_list[0].args[1]
        assert (
            body["payment_source"]["paypal"]["attributes"]["vault"]["store_in_vault"]
            == "ON_SUCCESS"
        )

    def test_get_form_reuses_existing_order(self):
        self.payment.extra_data = json.dumps({"ppcp_order": CREATE_ORDER_RESPONSE})
        api = self._mock_api(self.provider, [])
        with pytest.raises(RedirectNeeded):
            self.provider.get_form(self.payment)
        api.assert_not_called()

    def test_process_data_captures_and_confirms(self):
        self.payment.extra_data = json.dumps({"ppcp_order": CREATE_ORDER_RESPONSE})
        self._mock_api(self.provider, [capture_response()])
        request = self.factory.get(
            self.payment.get_process_url(),
            {"token": ORDER_ID, "PayerID": "PAYER123"},
        )
        response = self.provider.process_data(self.payment, request)
        assert self.payment.status == PaymentStatus.CONFIRMED
        assert response.url == self.payment.get_success_url()
        # Assert on PERSISTED state: change_status saves only status+message,
        # so the provider must have explicitly saved the capture bookkeeping.
        assert self.payment.persisted["transaction_id"] == CAPTURE_ID
        assert self.payment.persisted["captured_amount"] == self.payment.total
        assert "ppcp_capture" in json.loads(self.payment.persisted["extra_data"])

    def test_process_data_stores_vault_token(self):
        self.payment.extra_data = json.dumps({"ppcp_order": CREATE_ORDER_RESPONSE})
        self._mock_api(self.vault_provider, [capture_response(vault=VAULT_ID)])
        request = self.factory.get(
            self.payment.get_process_url(),
            {"token": ORDER_ID, "PayerID": "PAYER123"},
        )
        self.vault_provider.process_data(self.payment, request)
        assert self.payment.status == PaymentStatus.CONFIRMED
        token, kwargs = self.payment.renew_token_calls[0]
        assert token == VAULT_ID
        assert kwargs == {}

    def test_process_data_without_approval_rejects(self):
        self.payment.extra_data = json.dumps({"ppcp_order": CREATE_ORDER_RESPONSE})
        api = self._mock_api(self.provider, [])
        request = self.factory.get(self.payment.get_process_url(), {"token": ORDER_ID})
        response = self.provider.process_data(self.payment, request)
        assert self.payment.status == PaymentStatus.REJECTED
        assert response.url == self.payment.get_failure_url()
        api.assert_not_called()

    def test_process_data_order_mismatch_fails(self):
        self.payment.extra_data = json.dumps({"ppcp_order": CREATE_ORDER_RESPONSE})
        self._mock_api(self.provider, [])
        request = self.factory.get(
            self.payment.get_process_url(),
            {"token": "OTHER-ORDER", "PayerID": "PAYER123"},
        )
        with pytest.raises(PaymentError):
            self.provider.process_data(self.payment, request)

    def test_process_data_already_confirmed_is_idempotent(self):
        self.payment.status = PaymentStatus.CONFIRMED
        api = self._mock_api(self.provider, [])
        request = self.factory.get(
            self.payment.get_process_url(),
            {"token": ORDER_ID, "PayerID": "PAYER123"},
        )
        response = self.provider.process_data(self.payment, request)
        assert response.url == self.payment.get_success_url()
        api.assert_not_called()

    def test_autocomplete_with_wallet_charges_vault_token(self):
        self.payment.renew_token = VAULT_ID
        api = self._mock_api(self.vault_provider, [capture_response()])
        self.vault_provider.autocomplete_with_wallet(self.payment)
        assert self.payment.status == PaymentStatus.CONFIRMED
        assert self.payment.persisted["transaction_id"] == CAPTURE_ID
        assert "ppcp_capture" in json.loads(self.payment.persisted["extra_data"])
        body = api.call_args_list[0].args[1]
        assert body["payment_source"]["token"] == {
            "id": VAULT_ID,
            "type": "PAYMENT_METHOD_TOKEN",
        }

    def test_autocomplete_with_wallet_captures_created_order(self):
        self.payment.renew_token = VAULT_ID
        created = {"id": ORDER_ID, "status": "CREATED"}
        self._mock_api(self.vault_provider, [created, capture_response()])
        self.vault_provider.autocomplete_with_wallet(self.payment)
        assert self.payment.status == PaymentStatus.CONFIRMED

    def test_autocomplete_with_wallet_without_token_fails(self):
        with pytest.raises(PaymentError):
            self.provider.autocomplete_with_wallet(self.payment)

    def test_refund(self):
        self.payment.transaction_id = CAPTURE_ID
        self.payment.captured_amount = self.payment.total
        api = self._mock_api(self.provider, [{"status": "COMPLETED"}])
        refunded = self.provider.refund(self.payment, Decimal("5.00"))
        assert refunded == Decimal("5.00")
        url = api.call_args_list[0].args[0]
        assert CAPTURE_ID in url

    def test_refund_without_capture_fails(self):
        with pytest.raises(PaymentError):
            self.provider.refund(self.payment)

    def test_get_access_token_caches(self):
        with patch("payments.paypal.ppcp.requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.json.return_value = OAUTH_RESPONSE
            token1 = self.provider.get_access_token()
            token2 = self.provider.get_access_token()
        assert token1 == "Bearer A21AAFs"
        assert token1 == token2
        assert mock_post.call_count == 1

    def test_init_rejects_unknown_kwargs(self):
        with pytest.raises(TypeError):
            PaypalPPCPProvider(
                client_id="client-id",
                secret="secret",
                unexpected_option=True,
            )

    def test_init_rejects_preauthorization(self):
        """capture=False (pre-authorization) is not implemented yet.

        The legacy PaypalProvider authorizes in this mode; failing at
        configuration time prevents a migrating integrator from silently
        capturing payments they meant to only authorize.
        """
        with pytest.raises(NotImplementedError):
            PaypalPPCPProvider(
                client_id="client-id",
                secret="secret",
                capture=False,
            )

    def test_api_post_sends_idempotency_header(self):
        self.provider.get_access_token = MagicMock(return_value="Bearer A21AAFs")
        with patch("payments.paypal.ppcp.requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.json.return_value = {"id": ORDER_ID}
            result = self.provider.api_post(
                self.provider.orders_url, {"intent": "CAPTURE"}, request_id="create-x"
            )
        assert result == {"id": ORDER_ID}
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["PayPal-Request-Id"] == "create-x"
        assert headers["Authorization"] == "Bearer A21AAFs"

    def test_api_post_logs_and_raises_on_error(self):
        self.provider.get_access_token = MagicMock(return_value="Bearer A21AAFs")
        with patch("payments.paypal.ppcp.requests.post") as mock_post:
            mock_post.return_value.ok = False
            mock_post.return_value.status_code = 422
            mock_post.return_value.text = '{"name": "UNPROCESSABLE_ENTITY"}'
            mock_post.return_value.raise_for_status.side_effect = requests.HTTPError(
                "422"
            )
            with (
                self.assertLogs("payments.paypal.ppcp", level="WARNING"),
                pytest.raises(requests.HTTPError),
            ):
                self.provider.api_post(self.provider.orders_url)

    def test_get_form_saves_unsaved_payment(self):
        self.payment.id = None
        self._mock_api(self.provider, [CREATE_ORDER_RESPONSE])
        with pytest.raises(RedirectNeeded):
            self.provider.get_form(self.payment)
        assert self.payment.saved

    def test_get_form_without_approval_link_fails(self):
        no_link_order = {"id": ORDER_ID, "status": "CREATED", "links": []}
        self._mock_api(self.provider, [no_link_order])
        with pytest.raises(PaymentError):
            self.provider.get_form(self.payment)

    def test_process_data_incomplete_capture_rejects(self):
        self.payment.extra_data = json.dumps({"ppcp_order": CREATE_ORDER_RESPONSE})
        self._mock_api(self.provider, [{"id": ORDER_ID, "status": "PENDING"}])
        request = self.factory.get(
            self.payment.get_process_url(),
            {"token": ORDER_ID, "PayerID": "PAYER123"},
        )
        response = self.provider.process_data(self.payment, request)
        assert self.payment.status == PaymentStatus.REJECTED
        assert response.url == self.payment.get_failure_url()

    def test_process_data_capture_without_capture_object_fails(self):
        self.payment.extra_data = json.dumps({"ppcp_order": CREATE_ORDER_RESPONSE})
        self._mock_api(
            self.provider,
            [{"id": ORDER_ID, "status": "COMPLETED", "purchase_units": []}],
        )
        request = self.factory.get(
            self.payment.get_process_url(),
            {"token": ORDER_ID, "PayerID": "PAYER123"},
        )
        with pytest.raises(PaymentError):
            self.provider.process_data(self.payment, request)

    def test_extract_capture_empty_captures_list_fails(self):
        with pytest.raises(PaymentError):
            PaypalPPCPProvider._extract_capture(
                {"id": ORDER_ID, "purchase_units": [{"payments": {"captures": []}}]}
            )

    def test_process_data_capture_without_fee_breakdown_confirms(self):
        response_without_fee = capture_response()
        del response_without_fee["purchase_units"][0]["payments"]["captures"][0][
            "seller_receivable_breakdown"
        ]
        self.payment.extra_data = json.dumps({"ppcp_order": CREATE_ORDER_RESPONSE})
        self._mock_api(self.provider, [response_without_fee])
        request = self.factory.get(
            self.payment.get_process_url(),
            {"token": ORDER_ID, "PayerID": "PAYER123"},
        )
        self.provider.process_data(self.payment, request)
        assert self.payment.status == PaymentStatus.CONFIRMED

    def test_autocomplete_with_wallet_api_error_sets_error_status(self):
        self.payment.renew_token = VAULT_ID
        self._mock_api(self.vault_provider, requests.HTTPError("boom"))
        self.vault_provider.autocomplete_with_wallet(self.payment)
        assert self.payment.status == PaymentStatus.ERROR

    def test_autocomplete_with_wallet_incomplete_capture_rejects(self):
        self.payment.renew_token = VAULT_ID
        created = {"id": ORDER_ID, "status": "CREATED"}
        still_pending = {"id": ORDER_ID, "status": "PENDING"}
        self._mock_api(self.vault_provider, [created, still_pending])
        self.vault_provider.autocomplete_with_wallet(self.payment)
        assert self.payment.status == PaymentStatus.REJECTED

    def test_autocomplete_with_wallet_without_fee_breakdown_confirms(self):
        response_without_fee = capture_response()
        del response_without_fee["purchase_units"][0]["payments"]["captures"][0][
            "seller_receivable_breakdown"
        ]
        self.payment.renew_token = VAULT_ID
        self._mock_api(self.vault_provider, [response_without_fee])
        self.vault_provider.autocomplete_with_wallet(self.payment)
        assert self.payment.status == PaymentStatus.CONFIRMED

    def test_refund_full_amount_without_argument(self):
        self.payment.transaction_id = CAPTURE_ID
        self.payment.captured_amount = self.payment.total
        api = self._mock_api(self.provider, [{"status": "COMPLETED"}])
        refunded = self.provider.refund(self.payment)
        assert refunded == self.payment.total
        body = api.call_args_list[0].args[1]
        assert body == {}

    def test_refund_failed_status_raises(self):
        self.payment.transaction_id = CAPTURE_ID
        self._mock_api(self.provider, [{"status": "FAILED"}])
        with pytest.raises(PaymentError):
            self.provider.refund(self.payment, Decimal("5.00"))

    def _mock_delete(self, status_code):
        self.provider.get_access_token = MagicMock(return_value="Bearer A21AAFs")
        patcher = patch("payments.paypal.ppcp.requests.delete")
        mock_delete = patcher.start()
        self.addCleanup(patcher.stop)
        mock_delete.return_value.status_code = status_code
        mock_delete.return_value.ok = status_code < 400
        if status_code >= 400:
            mock_delete.return_value.raise_for_status.side_effect = requests.HTTPError(
                str(status_code)
            )
        return mock_delete

    def test_erase_wallet(self):
        mock_delete = self._mock_delete(204)
        self.provider.erase_wallet(VAULT_ID)
        url = mock_delete.call_args.args[0]
        assert (
            url
            == "https://api-m.sandbox.paypal.com/v3/vault/payment-tokens/" + VAULT_ID
        )

    def test_erase_wallet_already_gone_is_ok(self):
        self._mock_delete(404)
        self.provider.erase_wallet(VAULT_ID)

    def test_erase_wallet_error_raises(self):
        self._mock_delete(500)
        with pytest.raises(requests.HTTPError):
            self.provider.erase_wallet(VAULT_ID)
