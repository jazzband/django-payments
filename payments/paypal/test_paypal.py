from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

from django.utils import timezone
from requests import HTTPError

from payments import PaymentError
from payments import PaymentStatus
from payments import PurchasedItem
from payments import RedirectNeeded

from . import PaypalCardProvider
from . import PaypalProvider

CLIENT_ID = "abc123"
PAYMENT_TOKEN = "5a4dae68-2715-4b1e-8bb2-2c2dbe9255f6"
SECRET = "123abc"
VARIANT = "wallet"

PROCESS_DATA = {
    "name": "John Doe",
    "number": "371449635398431",
    "expiration_0": "5",
    "expiration_1": date.today().year + 1,
    "cvv2": "1234",
}


class PaymentQuerySet(Mock):
    __payments = {}

    def create(self, **kwargs):
        if kwargs:
            raise NotImplementedError(f"arguments not supported yet: {kwargs}")
        id_ = max(self.__payments) + 1 if self.__payments else 1
        self.__payments[id_] = {}
        payment = Payment()
        payment.id = id_
        payment.save()
        return payment

    def get(self, *args, **kwargs):
        if args or kwargs:
            return self.filter(*args, **kwargs).get()
        payment = Payment()
        (payment_fields,) = self.__payments.values()
        for payment_field_name, payment_field_value in payment_fields.items():
            setattr(payment, payment_field_name, deepcopy(payment_field_value))
        return payment

    def filter(self, *args, pk=None, **kwargs):
        if args or kwargs:
            raise NotImplementedError(f"arguments not supported yet: {args}, {kwargs}")
        if pk is not None:
            return PaymentQuerySet(
                {pk_: payment for pk_, payment in self.__payments.items() if pk_ == pk}
            )
        return self

    def update(self, **kwargs):
        for payment in self.__payments.values():
            for field_name, field_value in kwargs.items():
                if not any(
                    field.name == field_name
                    for field in Payment._meta.get_fields(
                        include_parents=True, include_hidden=True
                    )
                ):
                    raise NotImplementedError(
                        f"updating unknown field not supported yet: {field_name}"
                    )
                payment[field_name] = deepcopy(field_value)

    def delete(self):
        self.__payments.clear()


class Payment(Mock):
    objects = PaymentQuerySet()

    id = 1
    description = "payment"
    currency = "USD"
    delivery = Decimal(10)
    status = PaymentStatus.WAITING
    tax = Decimal(10)
    token = PAYMENT_TOKEN
    total = Decimal(220)
    captured_amount = Decimal(0)
    variant = VARIANT
    transaction_id = None
    message = ""
    extra_data = json.dumps(
        {
            "links": {
                "approval_url": None,
                "capture": {"href": "http://capture.com"},
                "refund": {"href": "http://refund.com"},
                "execute": {"href": "http://execute.com"},
            }
        }
    )

    @property
    def pk(self):
        return self.id

    def change_status(self, status, message=""):
        self.status = status
        self.message = message
        self.save(update_fields=["status", "message"])

    def get_failure_url(self):
        return "http://cancel.com"

    def get_process_url(self):
        return "http://example.com"

    def get_purchased_items(self):
        return [
            PurchasedItem(
                name="foo", quantity=10, price=Decimal("20"), currency="USD", sku="bar"
            )
        ]

    def get_success_url(self):
        return "http://success.com"

    def save(self, *args, update_fields=None, **kwargs):
        if args or kwargs:
            raise NotImplementedError(f"arguments not supported yet: {args}, {kwargs}")
        if update_fields is None:
            update_fields = {
                field.name
                for field in self._meta.get_fields(
                    include_parents=True, include_hidden=True
                )
            }
        Payment.objects.filter(pk=self.pk).update(
            **{field: getattr(self, field) for field in update_fields}
        )

    def refresh_from_db(self, *args, **kwargs):
        if args or kwargs:
            raise NotImplementedError(f"arguments not supported yet: {args}, {kwargs}")
        payment_from_db = Payment.objects.get(pk=self.pk)
        for field in self._meta.get_fields(include_parents=True, include_hidden=True):
            field_value_from_db = getattr(payment_from_db, field.name)
            setattr(self, field.name, field_value_from_db)

    class Meta(Mock):
        def get_fields(self, include_parents=True, include_hidden=False):
            fields = []
            for field_name in {
                "id",
                "description",
                "currency",
                "delivery",
                "status",
                "tax",
                "token",
                "total",
                "captured_amount",
                "variant",
                "transaction_id",
                "message",
                "extra_data",
            }:
                field = Mock()
                field.name = field_name
                fields.append(field)
            return tuple(fields)

    _meta = Meta()


class TestPaypalProvider(TestCase):
    def setUp(self):
        Payment.objects.delete()
        self.payment = Payment.objects.create()
        self.provider = PaypalProvider(secret=SECRET, client_id=CLIENT_ID)

    def test_provider_raises_redirect_needed_on_success(self):
        with patch("requests.post") as mocked_post:
            transaction_id = "1234"
            data = MagicMock()
            data.return_value = {
                "id": transaction_id,
                "token_type": "test_token_type",
                "access_token": "test_access_token",
                "links": [{"rel": "approval_url", "href": "http://approval_url.com"}],
            }
            post = MagicMock()
            post.json = data
            post.status_code = 200
            mocked_post.return_value = post
            with self.assertRaises(RedirectNeeded):
                self.provider.get_form(payment=self.payment)
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        self.assertEqual(self.payment.captured_amount, Decimal("0"))
        self.assertEqual(self.payment.transaction_id, transaction_id)

    @patch("requests.post")
    def test_provider_captures_payment(self, mocked_post):
        data = MagicMock()
        data.return_value = {
            "state": "completed",
            "token_type": "test_token_type",
            "access_token": "test_access_token",
        }
        post = MagicMock()
        post.json = data
        post.status_code = 200
        mocked_post.return_value = post
        self.provider.capture(self.payment)
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)

    @patch("requests.post")
    def test_provider_handles_captured_payment(self, mocked_post):
        data = MagicMock()
        data.return_value = {"name": "AUTHORIZATION_ALREADY_COMPLETED"}
        response = MagicMock()
        response.json = data
        mocked_post.side_effect = HTTPError(response=response)
        self.provider.capture(self.payment)
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)

    @patch("requests.post")
    def test_provider_refunds_payment_fully(self, mocked_post):
        data = MagicMock()
        data.side_effect = [
            {
                "token_type": "test_token_type",
                "access_token": "test_access_token",
            },
            {"amount": {"total": "220.00", "currency": "USD"}},
        ]
        post = MagicMock()
        post.json = data
        post.status_code = 200
        mocked_post.return_value = post
        self.provider.refund(self.payment)
        mocked_post.assert_called_with(
            "http://refund.com",
            headers={
                "Content-Type": "application/json",
                "Authorization": "test_token_type test_access_token",
            },
            data="{}",
        )
        self.assertEqual(self.payment.status, PaymentStatus.REFUNDED)

    @patch("requests.post")
    def test_provider_refunds_payment_partially(self, mocked_post):
        data = MagicMock()
        data.side_effect = [
            {
                "token_type": "test_token_type",
                "access_token": "test_access_token",
            },
            {"amount": {"total": "1.00", "currency": "USD"}},
        ]
        post = MagicMock()
        post.json = data
        post.status_code = 200
        mocked_post.return_value = post
        self.provider.refund(self.payment, amount=Decimal(1))
        mocked_post.assert_called_with(
            "http://refund.com",
            headers={
                "Content-Type": "application/json",
                "Authorization": "test_token_type test_access_token",
            },
            data='{"amount": {"currency": "USD", "total": "1.00"}}',
        )
        self.assertEqual(self.payment.status, PaymentStatus.REFUNDED)

    @patch("requests.post")
    @patch("payments.paypal.redirect")
    def test_provider_redirects_on_success_captured_payment(
        self, mocked_redirect, mocked_post
    ):
        data = MagicMock()
        data.return_value = {
            "token_type": "test_token_type",
            "access_token": "test_access_token",
            "payer": {"payer_info": "test123"},
            "transactions": [
                {
                    "related_resources": [
                        {"sale": {"links": ""}, "authorization": {"links": ""}}
                    ]
                }
            ],
        }
        post = MagicMock()
        post.json = data
        post.status_code = 200
        mocked_post.return_value = post

        request = MagicMock()
        request.GET = {"token": "test", "PayerID": "1234"}
        self.provider.process_data(self.payment, request)

        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
        self.assertEqual(self.payment.captured_amount, self.payment.total)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
        self.assertEqual(self.payment.captured_amount, self.payment.total)

    @patch("requests.post")
    @patch("payments.paypal.redirect")
    def test_provider_redirects_on_success_preauth_payment(
        self, mocked_redirect, mocked_post
    ):
        data = MagicMock()
        data.return_value = {
            "token_type": "test_token_type",
            "access_token": "test_access_token",
            "payer": {"payer_info": "test123"},
            "transactions": [
                {
                    "related_resources": [
                        {"sale": {"links": ""}, "authorization": {"links": ""}}
                    ]
                }
            ],
        }
        post = MagicMock()
        post.json = data
        post.status_code = 200
        mocked_post.return_value = post

        request = MagicMock()
        request.GET = {"token": "test", "PayerID": "1234"}
        provider = PaypalProvider(secret=SECRET, client_id=CLIENT_ID, capture=False)
        provider.process_data(self.payment, request)

        self.assertEqual(self.payment.status, PaymentStatus.PREAUTH)
        self.assertEqual(self.payment.captured_amount, Decimal("0"))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.PREAUTH)
        self.assertEqual(self.payment.captured_amount, Decimal("0"))

    @patch("payments.paypal.redirect")
    def test_provider_request_without_payerid_redirects_on_failure(
        self, mocked_redirect
    ):
        request = MagicMock()
        request.GET = {"token": "test", "PayerID": None}
        self.provider.process_data(self.payment, request)
        self.assertEqual(self.payment.status, PaymentStatus.REJECTED)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.REJECTED)

    @patch("requests.post")
    def test_provider_renews_access_token(self, mocked_post):
        new_token = "new_test_token"
        response401 = MagicMock()
        response401.status_code = 401
        data = MagicMock()
        data.return_value = {"access_token": new_token, "token_type": "type"}
        response = MagicMock()
        response.json = data
        response.status_code = 200
        mocked_post.side_effect = [HTTPError(response=response401), response, response]

        self.payment.created = timezone.now()
        self.payment.extra_data = json.dumps(
            {
                "auth_response": {
                    "access_token": "expired_token",
                    "token_type": "token type",
                    "expires_in": 99999,
                }
            }
        )
        self.provider.create_payment(self.payment)
        payment_response = json.loads(self.payment.extra_data)["auth_response"]
        self.assertEqual(payment_response["access_token"], new_token)


class TestPaypalCardProvider(TestCase):
    def setUp(self):
        self.payment = Payment(extra_data="")
        self.provider = PaypalCardProvider(secret=SECRET, client_id=CLIENT_ID)

    def test_provider_raises_redirect_needed_on_success_captured_payment(self):
        with patch("requests.post") as mocked_post:
            transaction_id = "1234"
            data = MagicMock()
            data.return_value = {
                "id": transaction_id,
                "token_type": "test_token_type",
                "access_token": "test_access_token",
                "transactions": [
                    {
                        "related_resources": [
                            {
                                "sale": {
                                    "links": [
                                        {"rel": "refund", "href": "http://refund.com"}
                                    ]
                                }
                            }
                        ]
                    }
                ],
            }
            post = MagicMock()
            post.json = data
            post.status_code = 200
            mocked_post.return_value = post
            with self.assertRaises(RedirectNeeded) as exc:
                self.provider.get_form(payment=self.payment, data=PROCESS_DATA)
                self.assertEqual(exc.args[0], self.payment.get_success_url())
        links = self.provider._get_links(self.payment)
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
        self.assertEqual(self.payment.captured_amount, self.payment.total)
        self.assertEqual(self.payment.transaction_id, transaction_id)
        self.assertTrue("refund" in links)

    def test_provider_raises_redirect_needed_on_success_preauth_payment(self):
        provider = PaypalCardProvider(secret=SECRET, client_id=CLIENT_ID, capture=False)
        with patch("requests.post") as mocked_post:
            transaction_id = "1234"
            data = MagicMock()
            data.return_value = {
                "id": transaction_id,
                "token_type": "test_token_type",
                "access_token": "test_access_token",
                "transactions": [
                    {
                        "related_resources": [
                            {
                                "authorization": {
                                    "links": [
                                        {"rel": "refund", "href": "http://refund.com"},
                                        {
                                            "rel": "capture",
                                            "href": "http://capture.com",
                                        },
                                    ]
                                }
                            }
                        ]
                    }
                ],
            }
            post = MagicMock()
            post.json = data
            post.status_code = 200
            mocked_post.return_value = post
            with self.assertRaises(RedirectNeeded) as exc:
                provider.get_form(payment=self.payment, data=PROCESS_DATA)
                self.assertEqual(exc.args[0], self.payment.get_success_url())
        links = provider._get_links(self.payment)
        self.assertEqual(self.payment.status, PaymentStatus.PREAUTH)
        self.assertEqual(self.payment.captured_amount, Decimal("0"))
        self.assertEqual(self.payment.transaction_id, transaction_id)
        self.assertTrue("capture" in links)
        self.assertTrue("refund" in links)

    def test_form_shows_validation_error_message(self):
        with patch("requests.post") as mocked_post:
            error_message = "error message"
            data = MagicMock()
            data.return_value = {"details": [{"issue": error_message}]}
            post = MagicMock()
            post.json = data
            post.status_code = 400
            mocked_post.side_effect = HTTPError(response=post)
            form = self.provider.get_form(payment=self.payment, data=PROCESS_DATA)
        self.assertEqual(self.payment.status, PaymentStatus.ERROR)
        self.assertEqual(form.errors["__all__"][0], error_message)

    def test_form_shows_internal_error_message(self):
        with patch("requests.post") as mocked_post:
            error_message = "error message"
            data = MagicMock()
            data.return_value = {
                "token_type": "test_token_type",
                "access_token": "test_access_token",
                "message": error_message,
            }
            post = MagicMock()
            post.status_code = 400
            post.json = data
            mocked_post.return_value = post
            with self.assertRaises(PaymentError):
                self.provider.get_form(payment=self.payment, data=PROCESS_DATA)
        self.assertEqual(self.payment.status, PaymentStatus.ERROR)
        self.assertEqual(self.payment.message, error_message)
