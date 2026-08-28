from __future__ import annotations

import json
import logging
import time
from decimal import Decimal
from urllib.parse import urljoin

import requests
from django.shortcuts import redirect

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded
from payments.core import BasicProvider
from payments.core import get_base_url

logger = logging.getLogger(__name__)

TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 30


class WalletTokenRevoked(PaymentError):
    """PayPal no longer holds the vaulted payment method for this payer.

    Raised instead of a plain error status so the caller can disarm
    automatic billing: every future charge against this token fails the
    same way, and retrying it forever only accumulates failed payments.
    """


class PaypalPPCPProvider(BasicProvider):
    """PayPal Complete Payments provider (Orders API v2 + Vault).

    This is the modern PayPal provider: PayPal has deprecated the v1
    Payments API used by :class:`~payments.paypal.PaypalProvider`, and new
    integrations should use this provider instead.

    Checkout uses the redirect (approval-link) flow: an order is created
    via the Orders v2 API, the user approves it on PayPal's page, and the
    payment is captured synchronously when they return.

    With ``vault=True`` the provider implements the wallet interface (see
    :doc:`/wallet`): the user's consent to future charges is requested
    during checkout (``store_in_vault``), the resulting vault payment token
    is handed to ``payment.set_renew_token()``, and later payments can be
    charged server-side through ``autocomplete_with_wallet()`` without any
    user interaction (merchant-initiated transactions).

    :param client_id: Client ID of your PayPal REST application
    :param secret: Secret of your PayPal REST application
    :param endpoint: The API endpoint to use. For the sandbox environment,
        use ``'https://api-m.sandbox.paypal.com'``
    :param capture: Whether to capture the payment automatically
    :param vault: Store the payment method on successful checkout and
        enable server-initiated recurring charges (the wallet interface)
    :param brand_name: Merchant name shown on the PayPal review page
    """

    def __init__(
        self,
        client_id: str,
        secret: str,
        endpoint: str = "https://api-m.paypal.com",
        capture: bool = True,
        vault: bool = False,
        brand_name: str = "",
    ) -> None:
        if not capture:
            # The legacy PaypalProvider authorizes with capture=False; this
            # provider only implements intent=CAPTURE so far. Fail at
            # configuration time rather than silently capturing.
            raise NotImplementedError(
                "PaypalPPCPProvider does not support pre-authorization "
                "(capture=False) yet"
            )
        self.client_id = client_id
        self.secret = secret
        self.endpoint = endpoint
        self.vault = vault
        self.brand_name = brand_name
        self.oauth2_url = endpoint + "/v1/oauth2/token"
        self.orders_url = endpoint + "/v2/checkout/orders"
        self.captures_url = endpoint + "/v2/payments/captures"
        self.vault_tokens_url = endpoint + "/v3/vault/payment-tokens"
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        super().__init__(capture=capture)

    # -- HTTP layer --------------------------------------------------------

    def get_access_token(self) -> str:
        """Return a cached OAuth2 access token, fetching a new one if needed."""
        now = time.monotonic()
        if (
            self._access_token
            and now < self._access_token_expires_at - TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS
        ):
            return self._access_token
        response = requests.post(
            self.oauth2_url,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.secret),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        self._access_token = "{} {}".format(data["token_type"], data["access_token"])
        self._access_token_expires_at = now + data.get("expires_in", 300)
        return self._access_token

    def api_post(self, url, json_body=None, request_id=None) -> dict:
        """Perform an authorized POST request to the PayPal API.

        :param url: full API URL to post to
        :param json_body: JSON-serializable request body
        :param request_id: value for the ``PayPal-Request-Id`` idempotency
            header; a retried call (timeout, double click on the return URL)
            then replays the original result instead of double-charging
        :returns: JSON response data from the PayPal API
        :raises requests.HTTPError: if the API returns an error status code
        """
        headers = {
            "Authorization": self.get_access_token(),
            "Content-Type": "application/json",
        }
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        response = requests.post(
            url,
            json=json_body if json_body is not None else {},
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if not response.ok:
            logger.warning(
                "PayPal PPCP API error: url=%s status=%s body=%s",
                url,
                response.status_code,
                response.text[:2000],
            )
        response.raise_for_status()
        return response.json()

    # -- payment extra_data helpers ----------------------------------------

    @staticmethod
    def _get_attr(payment, key):
        extra_data = json.loads(payment.extra_data or "{}")
        return extra_data.get(key)

    @staticmethod
    def _set_attr(payment, key, value) -> None:
        extra_data = json.loads(payment.extra_data or "{}")
        extra_data[key] = value
        payment.extra_data = json.dumps(extra_data)

    # -- checkout flow -----------------------------------------------------

    def get_form(self, payment, data=None):
        """Create the PayPal order and redirect the buyer to approve it."""
        if not payment.id:
            payment.save()
        order_data = self._get_attr(payment, "ppcp_order")
        if not order_data:
            order_data = self.create_order(payment)
            self._set_attr(payment, "ppcp_order", order_data)
            payment.save()
        approve_url = self._get_link(order_data, ("payer-action", "approve"))
        if not approve_url:
            raise PaymentError(
                f"PayPal order {order_data.get('id')} has no approval link"
            )
        payment.change_status(PaymentStatus.WAITING)
        raise RedirectNeeded(approve_url)

    def create_order(self, payment) -> dict:
        """Create an Orders v2 order for this payment."""
        experience_context = {
            "return_url": self.get_return_url(payment),
            "cancel_url": urljoin(get_base_url(), payment.get_failure_url()),
            "user_action": "PAY_NOW",
            "shipping_preference": "NO_SHIPPING",
        }
        if self.brand_name:
            experience_context["brand_name"] = self.brand_name
        paypal_source: dict = {"experience_context": experience_context}
        if self.vault:
            paypal_source["attributes"] = {
                "vault": {
                    "store_in_vault": "ON_SUCCESS",
                    "usage_type": "MERCHANT",
                    "customer_type": "CONSUMER",
                }
            }
        body = {
            "intent": "CAPTURE",
            "purchase_units": [self.get_purchase_unit(payment)],
            "payment_source": {"paypal": paypal_source},
        }
        return self.api_post(
            self.orders_url, body, request_id=f"create-{payment.token}"
        )

    def get_purchase_unit(self, payment) -> dict:
        return {
            "amount": {
                "currency_code": payment.currency,
                "value": str(payment.total),
            },
            "description": (payment.description or "")[:127],
            "custom_id": str(payment.pk),
        }

    @staticmethod
    def _get_link(order_data, rels):
        for link in order_data.get("links", []):
            if link.get("rel") in rels:
                return link.get("href")
        return None

    def process_data(self, payment, request):
        """Handle the buyer returning from PayPal: capture the order."""
        if payment.status == PaymentStatus.CONFIRMED:
            # Buyer reloaded the return URL of an already-captured payment.
            return redirect(payment.get_success_url())

        order_data = self._get_attr(payment, "ppcp_order") or {}
        order_id = order_data.get("id")
        returned_order_id = request.GET.get("token")
        if not order_id or returned_order_id != order_id:
            raise PaymentError(
                f"PayPal return does not match payment: "
                f"expected order {order_id}, got {returned_order_id}"
            )
        if not request.GET.get("PayerID"):
            # Buyer landed on the return URL without approving the order.
            payment.change_status(PaymentStatus.REJECTED, "Buyer did not approve")
            return redirect(payment.get_failure_url())

        capture_data = self.api_post(
            f"{self.orders_url}/{order_id}/capture",
            request_id=f"capture-{payment.token}",
        )
        self._set_attr(payment, "ppcp_capture", capture_data)
        return self._apply_capture_result(payment, capture_data)

    def _apply_capture_result(self, payment, capture_data):
        # change_status() persists ONLY status+message (update_fields), so
        # every bookkeeping field must be saved explicitly before calling it.
        if capture_data.get("status") != "COMPLETED":
            payment.save()
            payment.change_status(
                PaymentStatus.REJECTED,
                f"PayPal order status: {capture_data.get('status')}",
            )
            return redirect(payment.get_failure_url())

        capture = self._extract_capture(capture_data)
        if capture.get("status") != "COMPLETED":
            self._hold_pending_capture(payment, capture)
            return redirect(payment.get_success_url())
        self._book_capture(payment, capture)

        vault_data = (
            capture_data.get("payment_source", {})
            .get("paypal", {})
            .get("attributes", {})
            .get("vault", {})
        )
        if self.vault and vault_data.get("id"):
            payment.set_renew_token(vault_data["id"])

        payment.change_status(PaymentStatus.CONFIRMED)
        self._finalize_wallet_payment(payment)
        return redirect(payment.get_success_url())

    @staticmethod
    def _extract_capture(capture_data) -> dict:
        purchase_units = capture_data.get("purchase_units", [])
        if purchase_units:
            captures = purchase_units[0].get("payments", {}).get("captures", [])
            if captures:
                return captures[0]
        raise PaymentError(
            f"PayPal capture response has no capture object: "
            f"order {capture_data.get('id')}"
        )

    def _book_capture(self, payment, capture) -> None:
        """Persist the settled capture's bookkeeping on the payment.

        Saves explicitly because a later ``change_status()`` persists only
        status and message. Subclasses can override this to store extra
        bookkeeping from the capture object — e.g. the PayPal fee at
        ``capture["seller_receivable_breakdown"]["paypal_fee"]``.
        """
        payment.transaction_id = capture["id"]
        payment.captured_amount = payment.total
        payment.save()

    def _hold_pending_capture(self, payment, capture) -> None:
        """Keep a payment whose capture has not settled in WAITING.

        A capture can come back ``PENDING`` (eCheck funding, risk review)
        even when the order reports ``COMPLETED``. The money has not
        arrived, so nothing is booked and the payment must not confirm.
        The capture id is persisted so the payment can be reconciled once
        PayPal settles the capture.
        """
        payment.transaction_id = capture.get("id", "")
        payment.save()
        reason = capture.get("status_details", {}).get("reason")
        message = f"PayPal capture {capture.get('status')}" + (
            f": {reason}" if reason else ""
        )
        logger.warning(
            "Payment %s: %s -- awaiting settlement, nothing booked",
            payment.pk,
            message,
        )
        payment.change_status(PaymentStatus.WAITING, message)

    # -- webhook events ----------------------------------------------------

    def apply_capture_webhook(self, payment, capture) -> str | None:
        """Apply a ``PAYMENT.CAPTURE.*`` webhook resource to the payment.

        This is how an unsettled capture (eCheck funding, risk review)
        eventually resolves, and how a capture PayPal denies or reverses
        after the fact reaches the integration - neither shows up in the
        synchronous return flow. Returns the new status, or ``None`` when
        the event required no change.

        A confirmed payment is never demoted by a later DENIED event:
        PayPal can deliver events out of order, and only a genuine refund
        may move a payment out of confirmed.

        Webhook *transport* (signature verification, payment lookup) is the
        integration's business - see the webhook section in the docs.
        """
        status = capture.get("status")
        self._set_attr(payment, "ppcp_capture_webhook", capture)

        if status == "COMPLETED":
            if payment.status == PaymentStatus.CONFIRMED:
                payment.save()
                return None
            self._book_capture(payment, capture)
            payment.change_status(PaymentStatus.CONFIRMED)
            self._finalize_wallet_payment(payment)
            return PaymentStatus.CONFIRMED

        if status in ("DENIED", "FAILED", "DECLINED"):
            if payment.status == PaymentStatus.CONFIRMED:
                logger.warning(
                    "Ignoring PayPal %s webhook for already-confirmed payment %s",
                    status,
                    payment.pk,
                )
                payment.save()
                return None
            payment.save()
            payment.change_status(PaymentStatus.REJECTED, f"PayPal capture {status}")
            return PaymentStatus.REJECTED

        if status == "PENDING":
            self._hold_pending_capture(payment, capture)
            return PaymentStatus.WAITING

        logger.info(
            "Unhandled PayPal capture status %s for payment %s", status, payment.pk
        )
        payment.save()
        return None

    def apply_refund_webhook(self, payment, refund) -> str | None:
        """Apply a ``PAYMENT.CAPTURE.REFUNDED`` webhook resource to the payment.

        Only a refund of the whole captured amount flips the payment to
        REFUNDED; a partial refund is recorded and logged for a human,
        because the payment model has no partial-refund state to move to.
        """
        self._set_attr(payment, "ppcp_refund_webhook", refund)
        payment.save()

        amount = refund.get("amount", {}).get("value")
        refunded = Decimal(amount) if amount is not None else None

        if refunded is not None and refunded < payment.captured_amount:
            logger.warning(
                "Partial PayPal refund %s of %s for payment %s - needs manual"
                " reconciliation",
                refunded,
                payment.captured_amount,
                payment.pk,
            )
            return None

        payment.change_status(PaymentStatus.REFUNDED, "Refunded at PayPal")
        return PaymentStatus.REFUNDED

    # -- wallet interface (server-initiated recurring charges) -------------

    @staticmethod
    def _renewal_request_id(payment, step: str) -> str:
        """PayPal-Request-Id for a merchant-initiated renewal call.

        The default is scoped to the payment instance. Integrations whose
        retry logic creates a NEW payment row per attempt should override
        this with a key derived from what is being paid (and, typically, the
        calendar day): keyed on the row, a retry after a timeout is a fresh
        request and double-charges when the timed-out call actually reached
        PayPal; keyed on the target, PayPal replays the original result.
        """
        return f"renew-{step}-{payment.token}"

    @staticmethod
    def _is_token_gone(error: requests.HTTPError) -> bool:
        """True when PayPal says the vaulted payment method itself is gone.

        Deliberately narrow: only a 404 on the token resource counts,
        because a false positive disarms a paying customer's automatic
        billing. Declines, rate limits and outages stay transient errors.
        The issue codes are logged so integrations can widen this from real
        production data.
        """
        response = getattr(error, "response", None)
        if response is None:
            return False
        try:
            details = response.json().get("details", [])
        except ValueError:
            details = []
        issues = [d.get("issue") for d in details if isinstance(d, dict)]
        if issues:
            logger.warning(
                "PayPal renewal error %s, issues: %s", response.status_code, issues
            )
        return response.status_code == 404

    def autocomplete_with_wallet(self, payment) -> None:
        """Charge the vaulted PayPal payment token (merchant-initiated)."""
        renew_token = payment.get_renew_token()
        if not renew_token:
            raise PaymentError(f"No PayPal vault token to renew payment {payment.pk}")
        body = {
            "intent": "CAPTURE",
            "purchase_units": [self.get_purchase_unit(payment)],
            "payment_source": {
                "token": {"id": renew_token, "type": "PAYMENT_METHOD_TOKEN"}
            },
        }
        try:
            order_data = self.api_post(
                self.orders_url,
                body,
                request_id=self._renewal_request_id(payment, "order"),
            )
        except requests.HTTPError as e:
            if self._is_token_gone(e):
                payment.change_status(
                    PaymentStatus.ERROR, "PayPal payment method no longer available"
                )
                raise WalletTokenRevoked(
                    f"PayPal vault token for payment {payment.pk} no longer exists"
                ) from e
            payment.change_status(PaymentStatus.ERROR, f"PayPal renewal failed: {e}")
            return
        self._set_attr(payment, "ppcp_order", order_data)
        payment.save()
        if order_data.get("status") != "COMPLETED":
            # Some accounts return CREATED and need an explicit capture step.
            # Wrapped like the order call above: an unhandled error here would
            # escape into whatever schedules the renewals and could abort a
            # whole batch of unrelated accounts.
            try:
                order_data = self.api_post(
                    f"{self.orders_url}/{order_data['id']}/capture",
                    request_id=self._renewal_request_id(payment, "capture"),
                )
            except requests.HTTPError as e:
                payment.change_status(
                    PaymentStatus.ERROR, f"PayPal renewal capture failed: {e}"
                )
                return
        self._set_attr(payment, "ppcp_capture", order_data)
        if order_data.get("status") != "COMPLETED":
            payment.save()
            payment.change_status(
                PaymentStatus.REJECTED,
                f"PayPal renewal order status: {order_data.get('status')}",
            )
            return
        capture = self._extract_capture(order_data)
        if capture.get("status") != "COMPLETED":
            self._hold_pending_capture(payment, capture)
            return
        self._book_capture(payment, capture)
        payment.change_status(PaymentStatus.CONFIRMED)
        self._finalize_wallet_payment(payment)

    def erase_wallet(self, token) -> None:
        """Delete the vaulted payment method (cancels future renewals).

        A 404 means the token is already gone at PayPal and is treated as
        success, so erasing twice stays idempotent.
        """
        response = requests.delete(
            f"{self.vault_tokens_url}/{token}",
            headers={"Authorization": self.get_access_token()},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            logger.warning("PayPal vault token already deleted: %s", token)
            return
        response.raise_for_status()

    # -- refunds -----------------------------------------------------------

    def refund(self, payment, amount=None) -> Decimal:
        if not payment.transaction_id:
            raise PaymentError(f"Payment {payment.pk} has no PayPal capture to refund")
        body = {}
        if amount is not None:
            body["amount"] = {
                "currency_code": payment.currency,
                "value": str(amount),
            }
        refund_data = self.api_post(
            f"{self.captures_url}/{payment.transaction_id}/refund",
            body,
            request_id=f"refund-{payment.token}-{amount}",
        )
        self._set_attr(payment, "ppcp_refund", refund_data)
        payment.save()
        if refund_data.get("status") not in ("COMPLETED", "PENDING"):
            raise PaymentError(
                f"PayPal refund failed with status {refund_data.get('status')}"
            )
        return amount if amount is not None else payment.captured_amount
