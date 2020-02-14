from __future__ import unicode_literals

import json

from decimal import Decimal
from unittest import TestCase
from mock import MagicMock, Mock, patch

from . import PayuApiError, PayuProvider
from .. import PaymentStatus, PurchasedItem, RedirectNeeded

SECRET = '123abc'
SECOND_KEY = '123abc'
POS_ID = '123abc'
VARIANT = 'wallet'

PROCESS_DATA = {
    'name': 'John Doe',
    'number': '371449635398431',
    'expiration_0': '5',
    'expiration_1': '2020',
    'cvv2': '1234'}


class JSONEquals(str):
    def __init__(self, json):
        self.json = json

    def __eq__(self, other):
        return self.json == json.loads(other)


class Payment(Mock):
    id = 1
    description = 'payment'
    currency = 'USD'
    delivery = Decimal(10)
    status = PaymentStatus.WAITING
    tax = Decimal(10)
    total = Decimal(220)
    billing_first_name = "Foo"
    billing_last_name = "Bar"
    captured_amount = Decimal(0)
    variant = VARIANT
    transaction_id = None
    message = ''
    customer_ip_address = "123"
    token = "bar_token"
    extra_data = json.dumps({'links': {
        'approval_url': None,
        'capture': {'href': 'http://capture.com'},
        'refund': {'href': 'http://refund.com'},
        'execute': {'href': 'http://execute.com'}
    }})

    def change_status(self, status, message=''):
        self.status = status
        self.message = message

    def get_failure_url(self):
        return 'http://cancel.com'

    def get_process_url(self):
        return '/process_url/token'

    def get_payment_url(self):
        return '/payment/token'

    def get_purchased_items(self):
        return [
            PurchasedItem(
                name='foo', quantity=10, price=Decimal('20'),
                currency='USD', sku='bar')]

    def get_success_url(self):
        return 'http://foo_succ.com'

    def get_renew_token(self):
        return self.token

    def get_user_first_name(self):
        return "Foo"

    def get_user_last_name(self):
        return "Bar"

    def get_user_email(self):
        return "foo@bar.com"

    def set_renew_token(self, token, card_expire_year=None, card_expire_month=None):
        self.token = token
        self.card_expire_year = card_expire_year
        self.card_expire_month = card_expire_month


class TestPayuProvider(TestCase):
    urls = 'myapp.test_urls'

    def setUp(self):
        self.payment = Payment()

    def set_up_provider(self, recurring, express):
        with patch('requests.post') as mocked_post:
            data = MagicMock()
            data = '{"access_token": "test_access_token"}'
            json.loads(data)
            post = MagicMock()
            post.text = data
            post.status_code = 200
            mocked_post.return_value = post
            self.provider = PayuProvider(
                client_secret=SECRET,
                second_key=SECOND_KEY,
                pos_id=POS_ID,
                base_payu_url="http://mock.url/",
                recurring_payments=recurring,
                express_payments=express,
            )

    def test_redirect_to_recurring_payment(self):
        """ Test that if the payment recurrence is set, the user is redirected to renew payment form """
        self.set_up_provider(True, True)
        form = self.provider.get_form(payment=self.payment)
        self.assertEqual(form.__class__.__name__, "RenewPaymentForm")
        self.assertEqual(form.action, "https://example.com/process_url/token")
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        self.assertEqual(self.payment.captured_amount, Decimal('0'))

    def test_redirect_payu(self):
        self.set_up_provider(True, False)
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.text = '{"redirectUri": "test_redirect_uri", "status": {"statusCode": "SUCCESS"}, "orderId": 123}'
            post.status_code = 200
            mocked_post.return_value = post
            with self.assertRaises(RedirectNeeded) as context:
                self.provider.get_form(payment=self.payment)
            self.assertEqual(context.exception.args[0], 'test_redirect_uri')

    def test_redirect_payu_store_token(self):
        self.set_up_provider(True, False)
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.text = json.dumps({
                "redirectUri": "test_redirect_uri",
                "status": {"statusCode": "SUCCESS"},
                "orderId": 123,
                "payMethods": {"payMethod": {
                    "value": 1211,
                    "card": {"expirationYear": 2021, "expirationMonth": 1},
                }},
            })
            post.status_code = 200
            mocked_post.return_value = post
            with self.assertRaises(RedirectNeeded) as context:
                self.provider.get_form(payment=self.payment)
            self.assertEqual(context.exception.args[0], 'test_redirect_uri')
            self.assertEqual(self.payment.token, 1211)

    def test_redirect_payu_unknown_status(self):
        self.set_up_provider(True, False)
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post_text = {
                "redirectUri": "test_redirect_uri",
                "status": {"statusCode": "FOO"},
                "orderId": 123,
            }
            post.text = json.dumps(post_text)
            post.status_code = 200
            mocked_post.return_value = post
            with self.assertRaises(PayuApiError) as context:
                self.provider.get_form(payment=self.payment)
            self.assertEqual(context.exception.args[0], post_text)

            mocked_post.assert_called_once_with(
                'http://mock.url/api/v2_1/orders/',
                allow_redirects=False,
                data=JSONEquals(
                    {"buyer": {
                        "email": "foo@bar.com", "language": "en", "lastName": "Bar", "firstName": "Foo", "phone": None,
                    },
                        "description": "payment", "totalAmount": 20000, "merchantPosId": "123abc", "customerIp": "123",
                        "notifyUrl": "https://example.com/process_url/token",
                        "products": [
                            {"currency": "USD", "name": "foo", "quantity": 10, "unitPrice": 20, "subUnit": 100},
                        ],
                        "continueUrl": "http://foo_succ.com", "currencyCode": "USD",
                    },
                ),
                headers={'Authorization': 'Bearer test_access_token', 'Content-Type': 'application/json'},
            )

    def test_redirect_payu_no_status_code(self):
        self.set_up_provider(True, False)
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post_text = {
                "redirectUri": "test_redirect_uri",
                "orderId": 123,
            }
            post.text = json.dumps(post_text)
            post.status_code = 200
            mocked_post.return_value = post
            with self.assertRaises(PayuApiError) as context:
                self.provider.get_form(payment=self.payment)
            self.assertEqual(context.exception.args[0], post_text)

            mocked_post.assert_called_once_with(
                'http://mock.url/api/v2_1/orders/',
                allow_redirects=False,
                data=JSONEquals(
                    {"buyer": {
                        "email": "foo@bar.com", "language": "en", "lastName": "Bar", "firstName": "Foo", "phone": None,
                    },
                        "description": "payment", "totalAmount": 20000, "merchantPosId": "123abc", "customerIp": "123",
                        "notifyUrl": "https://example.com/process_url/token",
                        "products": [
                            {"currency": "USD", "name": "foo", "quantity": 10, "unitPrice": 20, "subUnit": 100},
                        ],
                        "continueUrl": "http://foo_succ.com", "currencyCode": "USD",
                    },
                ),
                headers={'Authorization': 'Bearer test_access_token', 'Content-Type': 'application/json'},
            )

    def test_redirect_payu_unauthorized_status(self):
        self.set_up_provider(True, False)
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.text = json.dumps({
                "redirectUri": "test_redirect_uri",
                "status": {"statusCode": "UNAUTHORIZED"},
                "orderId": 123,
            })
            post.status_code = 200
            mocked_post.return_value = post
            with self.assertRaises(PayuApiError) as context:
                self.provider.get_form(payment=self.payment)
            self.assertEqual(context.exception.args[0], "Unable to regain authorization token")

            mocked_post.assert_called_with(
                'http://mock.url/pl/standard/user/oauth/authorize',
                data={
                    'grant_type': 'client_credentials', 'client_id': '123abc', 'client_secret': '123abc',
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )

    def test_get_access_token_trusted_merchant(self):
        self.set_up_provider(True, False)
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.text = json.dumps({
                "redirectUri": "test_redirect_uri",
                'token_type': 'test_token_type',
                'access_token': 'test_access_token',
            })
            post.status_code = 200
            mocked_post.return_value = post
            token = self.provider.get_access_token('123abc', '123abc', 'trusted_merchant', 'foo@bar.com', 123)
            self.assertEqual(token, "test_access_token")

            mocked_post.assert_called_with(
                'http://mock.url/pl/standard/user/oauth/authorize',
                data={
                    'grant_type': 'trusted_merchant', 'client_id': '123abc',
                    'client_secret': '123abc', 'email': 'foo@bar.com', 'ext_customer_id': 123,
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )

    def test_redirect_cvv_form(self):
        """ Test redirection to CVV form if requested by PayU """
        self.set_up_provider(True, True)
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.text = '{"redirectUri": "test_redirect_uri", "status": {"statusCode": "WARNING_CONTINUE_CVV"}, "orderId": 123}'
            post.status_code = 200
            mocked_post.return_value = post
            redirect = self.provider.process_data(payment=self.payment, request=post)
            self.assertEqual(redirect.__class__.__name__, "HttpResponseRedirect")
            self.assertEqual(redirect.url, "/payment/token")

            mocked_post.assert_called_once_with(
                'http://mock.url/api/v2_1/orders/',
                allow_redirects=False,
                data=JSONEquals(
                    {
                        "products":
                        [
                            {"currency": "USD", "quantity": 10, "name": "foo", "unitPrice": 20, "subUnit": 100}
                        ],
                        "buyer": {
                            "phone": None, "email": "foo@bar.com", "lastName": "Bar", "language": "en", "firstName": "Foo",
                        },
                        "merchantPosId": "123abc", "notifyUrl": "https://example.com/process_url/token",
                        "payMethods": {
                            "payMethod": {
                                "value": "bar_token", "type": "CARD_TOKEN"
                            }
                        },
                        "totalAmount": 20000, "continueUrl": "http://foo_succ.com", "customerIp": "123", "description": "payment",
                        "recurring": "STANDARD", "currencyCode": "USD"
                    },
                ),
                headers={'Authorization': 'Bearer test_access_token', 'Content-Type': 'application/json'},
            )

    def test_showing_cvv_form(self):
        """ Test redirection to CVV form if requested by PayU """
        self.set_up_provider(True, True)
        self.payment.extra_data = json.dumps({'cvv_url': "foo_url"})
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.text = '{"redirectUri": "http://test_redirect_uri.com/", "status": {"statusCode": "SUCCESS"}, "orderId": 123}'
            post.status_code = 200
            mocked_post.return_value = post
            form = self.provider.get_form(payment=self.payment)
            self.assertEqual(form.__class__.__name__, "WidgetPaymentForm")
            self.assertTrue("payu-widget" in form.fields['script'].widget.render('a', 'b'))
            self.assertTrue("https://example.com/process_url/token" in form.fields['script'].widget.render('a', 'b'))
            self.assertTrue("cvv-url=foo_url" in form.fields['script'].widget.render('a', 'b'))

    def test_redirect_3ds_form(self):
        """ Test redirection to 3DS page if requested by PayU """
        self.set_up_provider(True, False)
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.text = '{"redirectUri": "test_redirect_uri", "status": {"statusCode": "WARNING_CONTINUE_3DS"}, "orderId": 123}'
            post.status_code = 200
            mocked_post.return_value = post
            with self.assertRaises(RedirectNeeded) as context:
                self.provider.get_form(payment=self.payment)
            mocked_post.assert_called_once_with(
                'http://mock.url/api/v2_1/orders/',
                allow_redirects=False,
                data=JSONEquals(
                    {
                        "merchantPosId": "123abc", "continueUrl": "http://foo_succ.com",
                        "buyer": {"lastName": "Bar", "phone": None, "email": "foo@bar.com", "firstName": "Foo", "language": "en"},
                        "description": "payment", "notifyUrl": "https://example.com/process_url/token", "totalAmount": 20000,
                        "currencyCode": "USD",
                        "products": [{"name": "foo", "quantity": 10, "subUnit": 100, "currency": "USD", "unitPrice": 20}],
                        "customerIp": "123"
                    },
                ),
                headers={'Authorization': 'Bearer test_access_token', 'Content-Type': 'application/json'},
            )
            self.assertEqual(context.exception.args[0], 'test_redirect_uri')

    def test_payu_renew_form(self):
        """ Test showing PayU card form """
        self.set_up_provider(True, True)
        transaction_id = '1234'
        data = MagicMock()
        data.return_value = {
            'id': transaction_id,
            'token_type': 'test_token_type',
            'access_token': 'test_access_token',
            'links': [
                {'rel': 'approval_url', 'href': 'http://approval_url.com'}
            ]}
        post = MagicMock()
        post.json = data
        post.status_code = 200
        form = self.provider.get_form(payment=self.payment)
        self.assertEqual(form.__class__.__name__, "RenewPaymentForm")
        self.assertEqual(form.action, "https://example.com/process_url/token")
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        self.assertEqual(self.payment.captured_amount, Decimal('0'))

    def test_payu_widget_form(self):
        """ Test showing PayU card widget """
        self.set_up_provider(True, True)
        self.payment.token = None
        transaction_id = '1234'
        data = MagicMock()
        data.return_value = {
            'id': transaction_id,
            'token_type': 'test_token_type',
            'access_token': 'test_access_token',
            'links': [
                {'rel': 'approval_url', 'href': 'http://approval_url.com'}
            ]}
        post = MagicMock()
        post.json = data
        post.status_code = 200
        form = self.provider.get_form(payment=self.payment)
        self.assertEqual(form.__class__.__name__, "WidgetPaymentForm")
        self.assertTrue("payu-widget" in form.fields['script'].widget.render('a', 'b'))
        self.assertTrue("https://example.com/process_url/token" in form.fields['script'].widget.render('a', 'b'))
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        self.assertEqual(self.payment.captured_amount, Decimal('0'))

    def test_process_notification(self):
        """ Test processing PayU notification """
        self.set_up_provider(True, True)
        mocked_request = MagicMock()
        mocked_request.body = json.dumps({"order": {"status": "COMPLETED"}}).encode("utf8")
        mocked_request.META = {
            'CONTENT_TYPE': 'application/json',
            "HTTP_OPENPAYU_SIGNATURE": "signature=a12fbd21c48e69bedee18edf042b816c;algorithm=MD5",
        }
        mocked_request.status_code = 200
        ret_val = self.provider.process_data(payment=self.payment, request=mocked_request)
        self.assertEqual(ret_val.__class__.__name__, "HttpResponse")
        self.assertEqual(ret_val.status_code, 200)
        self.assertEqual(ret_val.content, b"ok")
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
        self.assertEqual(self.payment.captured_amount, Decimal('0'))

    def test_process_notification_error(self):
        """ Test processing PayU notification with wrong signature """
        self.set_up_provider(True, True)
        mocked_request = MagicMock()
        mocked_request.body = b'{}'
        mocked_request.META = {'CONTENT_TYPE': 'application/json', "HTTP_OPENPAYU_SIGNATURE": "signature=foo;algorithm=MD5"}
        ret_val = self.provider.process_data(payment=self.payment, request=mocked_request)
        self.assertEqual(ret_val.__class__.__name__, "HttpResponse")
        self.assertEqual(ret_val.status_code, 500)
        self.assertEqual(ret_val.content, b"not ok")
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        self.assertEqual(self.payment.captured_amount, Decimal('0'))

    def test_process_notification_error_malformed_post(self):
        """ Test processing PayU notification with malformed POST """
        self.set_up_provider(True, True)
        mocked_request = MagicMock()
        mocked_request.body = b'{}'
        mocked_request.META = {'CONTENT_TYPE': 'application/json'}
        with self.assertRaises(PayuApiError) as context:
            self.provider.process_data(payment=self.payment, request=mocked_request)
        self.assertEqual(context.exception.args[0], "Malformed POST")

    def test_process_first_renew(self):
        """ Test processing first renew """
        self.set_up_provider(True, True)
        self.payment.token = None
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.text = '{"status": {"statusCode": "SUCCESS"}, "orderId": 123}'
            post.status_code = 200
            mocked_post.POST = {'value': 'renew_token'}
            mocked_post.return_value = post
            response = self.provider.process_data(payment=self.payment, request=mocked_post)
            self.assertEqual(response.__class__.__name__, "HttpResponse")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"http://foo_succ.com")
            mocked_post.assert_called_once_with(
                'http://mock.url/api/v2_1/orders/',
                allow_redirects=False,
                data=JSONEquals(
                    {
                        "recurring": "FIRST", "customerIp": "123", "totalAmount": 20000,
                        "description": "payment",
                        "products": [{"name": "foo", "subUnit": 100, "currency": "USD", "unitPrice": 20, "quantity": 10}],
                        "continueUrl": "http://foo_succ.com", "merchantPosId": "123abc", "currencyCode": "USD",
                        "payMethods": {"payMethod": {"value": "renew_token", "type": "CARD_TOKEN"}},
                        "buyer": {"firstName": "Foo", "email": "foo@bar.com", "language": "en", "phone": None, "lastName": "Bar"},
                        "notifyUrl": "https://example.com/process_url/token",
                    }
                ),
                headers={'Authorization': 'Bearer test_access_token', 'Content-Type': 'application/json'},
            )
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        self.assertEqual(self.payment.captured_amount, Decimal('0'))

    def test_process_renew(self):
        """ Test processing renew """
        self.set_up_provider(True, True)
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.text = '{"redirectUri": "http://test_redirect_uri.com/", "status": {"statusCode": "SUCCESS"}, "orderId": 123}'
            post.status_code = 200
            mocked_post.return_value = post
            redirect = self.provider.process_data(payment=self.payment, request=mocked_post)
            self.assertEqual(redirect.__class__.__name__, "HttpResponseRedirect")
            self.assertEqual(redirect.url, "http://test_redirect_uri.com/")
            mocked_post.assert_called_once_with(
                'http://mock.url/api/v2_1/orders/',
                allow_redirects=False,
                data=JSONEquals(
                    {
                        "products":
                        [
                            {"currency": "USD", "quantity": 10, "name": "foo", "unitPrice": 20, "subUnit": 100}
                        ],
                        "buyer": {
                            "phone": None, "email": "foo@bar.com", "lastName": "Bar", "language": "en", "firstName": "Foo",
                        },
                        "merchantPosId": "123abc", "notifyUrl": "https://example.com/process_url/token",
                        "payMethods": {
                            "payMethod": {
                                "value": "bar_token", "type": "CARD_TOKEN"
                            }
                        },
                        "totalAmount": 20000, "continueUrl": "http://foo_succ.com", "customerIp": "123", "description": "payment",
                        "recurring": "STANDARD", "currencyCode": "USD"
                    },
                ),
                headers={'Authorization': 'Bearer test_access_token', 'Content-Type': 'application/json'},
            )
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        self.assertEqual(self.payment.captured_amount, Decimal('0'))

    def test_process_renew_card_on_file(self):
        """ Test processing renew """
        self.set_up_provider(True, True)
        self.provider.card_on_file = True
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.text = '{"redirectUri": "http://test_redirect_uri.com/", "status": {"statusCode": "SUCCESS"}, "orderId": 123}'
            post.status_code = 200
            mocked_post.return_value = post
            redirect = self.provider.process_data(payment=self.payment, request=mocked_post)
            self.assertEqual(redirect.__class__.__name__, "HttpResponseRedirect")
            self.assertEqual(redirect.url, "http://test_redirect_uri.com/")
            mocked_post.assert_called_once_with(
                'http://mock.url/api/v2_1/orders/',
                allow_redirects=False,
                data=JSONEquals(
                    {
                        "products":
                        [
                            {"currency": "USD", "quantity": 10, "name": "foo", "unitPrice": 20, "subUnit": 100}
                        ],
                        "buyer": {
                            "phone": None, "email": "foo@bar.com", "lastName": "Bar", "language": "en", "firstName": "Foo",
                        },
                        "merchantPosId": "123abc", "notifyUrl": "https://example.com/process_url/token",
                        "payMethods": {
                            "payMethod": {
                                "value": "bar_token", "type": "CARD_TOKEN"
                            }
                        },
                        "totalAmount": 20000, "continueUrl": "http://foo_succ.com", "customerIp": "123", "description": "payment",
                        "cardOnFile": "STANDARD_CARDHOLDER", "currencyCode": "USD"
                    },
                ),
                headers={'Authorization': 'Bearer test_access_token', 'Content-Type': 'application/json'},
            )
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        self.assertEqual(self.payment.captured_amount, Decimal('0'))

    def test_auto_complete_recurring(self):
        """ Test processing renew. The function should return 'success' string, if nothing is required from user. """
        self.set_up_provider(True, True)
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.text = '{"status": {"statusCode": "SUCCESS"}, "orderId": 123}'
            post.status_code = 200
            mocked_post.return_value = post
            redirect = self.provider.auto_complete_recurring(self.payment)
            self.assertEqual(redirect, "success")
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        self.assertEqual(self.payment.captured_amount, Decimal('0'))

    def test_auto_complete_recurring_cvv2(self):
        """ Test processing renew when cvv2 form is required - it should return the payment processing URL """
        self.set_up_provider(True, True)
        with patch('requests.post') as mocked_post:
            post = MagicMock()
            post.text = '{"redirectUri": "test_redirect_uri", "status": {"statusCode": "WARNING_CONTINUE_CVV"}, "orderId": 123}'
            post.status_code = 200
            mocked_post.return_value = post
            redirect = self.provider.auto_complete_recurring(self.payment)
            self.assertEqual(redirect, "https://example.com/payment/token")
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
        self.assertEqual(self.payment.captured_amount, Decimal('0'))

    def test_delete_card_token(self):
        """ Test delete_card_token() """
        self.set_up_provider(True, True)
        self.payment.transaction_id = '1234'
        with patch('requests.delete') as mocked_post:
            post = MagicMock()
            post.text = '{"status": {"statusCode": "SUCCESS"}}'
            post.status_code = 204
            mocked_post.return_value = post
            rejected = self.provider.delete_card_token("FOO_TOKEN")
            self.assertTrue(rejected)
            mocked_post.assert_called_with(
                'http://mock.url/api/v2_1/tokens/FOO_TOKEN',
                headers={'Authorization': 'Bearer test_access_token', 'Content-Type': 'application/json'},
            )

    def test_get_paymethod_tokens(self):
        """ Test delete_card_token() """
        self.set_up_provider(True, True)
        self.payment.transaction_id = '1234'
        with patch('requests.get') as mocked_post:
            post = MagicMock()
            post.text = json.dumps({'cardTokens': [{'name': 'Google Pay', 'status': 'ENABLED'}]})
            post.status_code = 200
            mocked_post.return_value = post
            rdict = self.provider.get_paymethod_tokens()
            self.assertEqual(rdict['cardTokens'][0]['name'], 'Google Pay')
            mocked_post.assert_called_with(
                'http://mock.url/api/v2_1/paymethods/',
                headers={'Authorization': 'Bearer test_access_token', 'Content-Type': 'application/json'},
            )

    def test_reject_order(self):
        """ Test processing renew """
        self.set_up_provider(True, True)
        self.payment.transaction_id = '1234'
        with patch('requests.delete') as mocked_post:
            post = MagicMock()
            post.text = '{"status": {"statusCode": "SUCCESS"}}'
            post.status_code = 200
            mocked_post.return_value = post
            rejected = self.provider.reject_order(self.payment)
            self.assertTrue(rejected)
            mocked_post.assert_called_with(
                'http://mock.url/api/v2_1/orders/1234',
                headers={'Authorization': 'Bearer test_access_token', 'Content-Type': 'application/json'},
            )
        self.assertEqual(self.payment.status, PaymentStatus.REJECTED)

    def test_reject_order_error(self):
        """ Test processing renew """
        self.set_up_provider(True, True)
        self.payment.transaction_id = '1234'
        with patch('requests.delete') as mocked_post:
            post = MagicMock()
            post.text = '{"status": {"statusCode": "FAIL"}}'
            post.status_code = 200
            mocked_post.return_value = post
            rejected = self.provider.reject_order(self.payment)
            self.assertFalse(rejected)
            mocked_post.assert_called_with(
                'http://mock.url/api/v2_1/orders/1234',
                headers={'Authorization': 'Bearer test_access_token', 'Content-Type': 'application/json'},
            )
        self.assertEqual(self.payment.status, PaymentStatus.WAITING)
