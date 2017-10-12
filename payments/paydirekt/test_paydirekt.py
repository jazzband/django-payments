# coding=utf-8
import simplejson as json
from decimal import Decimal

from unittest import TestCase
try:
    from unittest.mock import MagicMock, patch
except ImportError:
    from mock import MagicMock, patch

from . import PaydirektProvider
from .. import FraudStatus, PaymentError, PaymentStatus, RedirectNeeded
from ..testcommon import create_test_payment

VARIANT = 'paydirekt'
API_KEY = '87dbc6cd-91d2-4574-bcb5-2aaaf924386d'
SECRET = '9Tth0qty_9zplTyY0d_QbHYvKM4iSngjoipWO6VxAao='

sample_request_paydirekt = {'refundLimit': 110, 'orderAmount': Decimal('9.00'),
        'shippingAddress': {'addresseeGivenName': 'fooo', 'emailAddress': 'test@test.de', 'addresseeLastName': 'noch ein test', 'city': 'M\xc3\xbcnchen', 'street': 'fooo 23', 'zip': '23233', 'streetNr': '23', 'countryCode': 'DE'},
        'type': 'DIRECT_SALE',
        'callbackUrlStatusUpdates': 'https://example.com/payments/process/13119ad6-1df2-49e1-a719-a26225b9bc44/',
        'currency': 'EUR', 'totalAmount': Decimal('9.00'),
        'merchantOrderReferenceNumber': '59dbfc86:35',
        'redirectUrlAfterRejection': 'https://example.com/failure/',
        'redirectUrlAfterAgeVerificationFailure': 'https://example.com/failure/',
        'redirectUrlAfterSuccess': 'https://example.com/success/',
        'redirectUrlAfterCancellation': 'https://example.com/failure/'}

directsale_open_data = {
  "checkoutId" : "6be6a80d-ef67-47c8-a5bd-2461d11da24c",
  "merchantOrderReferenceNumber" : "order-A12223412",
  "checkoutStatus" : "OPEN"
}

directsale_approve_data = {
  "checkoutId" : "6be6a80d-ef67-47c8-a5bd-2461d11da24c",
  "merchantOrderReferenceNumber" : "order-A12223412",
  "checkoutStatus" : "APPROVED"
}

order_open_data = {
  "checkoutId" : "dcc6cebc-5d92-4212-bca9-a442a32448e1",
  "merchantOrderReferenceNumber" : "order-A12223412",
  "checkoutStatus" : "OPEN"
}
order_approve_data = {
  "checkoutId" : "dcc6cebc-5d92-4212-bca9-a442a32448e1",
  "merchantOrderReferenceNumber" : "order-A12223412",
  "checkoutStatus" : "APPROVED"
}
order_close_data = {
  "checkoutId" : "dcc6cebc-5d92-4212-bca9-a442a32448e1",
  "merchantOrderReferenceNumber" : "order-A12223413",
  "checkoutStatus" : "CLOSED"
}

capture_process_data = {
  "checkoutId" : "e8118aa3-5bcd-450c-9f10-3785cf94053e",
  "merchantOrderReferenceNumber" : "order-A12223412",
  "merchantCaptureReferenceNumber" : "capture-21323",
  "captureStatus" : "SUCCESSFUL",
  "transactionId" : "ae68fd9f-6e9d-4a14-8507-507ab72d4986"
}

refund_process_data = {
  "checkoutId" : "7be9023d-39c5-4f9e-ba22-2500e0d3aeb3",
  "transactionId" : "4faa3e79-93fb-47af-a65c-96b89d80700a",
  "merchantRefundReferenceNumber" : "refund-12345",
  "merchantReconciliationReferenceNumber" : "reconciliation-12345",
  "refundStatus" : "SUCCESSFUL"
}

token_retrieve = {
  "access_token" : "EeNDpcqKeTJmbHYYvLvAFB7lnEaS0n8m6WNxL4IvHcLDa3iJ6XngQncrvXHKfJ4fxXhd1WCuRFFl4q617gkQrbSTIl_OtFeg39USAQMQTjWfP-ylUCnXZuORN6Zmscn0NLVY3OMrsbAqm5lECST07DjQLtLz8JO7E5urwjxxMMDPeRpOxg8yvoV42tQ5-AVahFu3i19HWphh2IPpZoE73t9k0pFtL6zGqo6CgjIHWcouDgNAQtFbleJkQtxPRNkUM-g-qgVMI7NiUhLVtFkohBa8-wUd5MU49YmaIgJlCWuGH_c6WhJMf4ryGOzi7bsCwS2NPR9HEzVWvAOA8-aUMiX0ud81pOlaJTiEyV3AWj1DyqOS_bcWiCwov-Xj2uU26aleSQPdDxJmwTphifRVqFBbC2LVb74VkRdJneaLXH-gw_Ge4Vzq_a1-v-CRZVkC90x7iy5IjaSh12HWs73UV0WpFEWQlWTmdahX9VLMBr-DNvDr8vbxlEL_h5uI28t4A1kRHF_lIO7z3lE7JMWQbEh-REEOH68yCK3nPx5_yVnsnFBNwXMSPBVP5ShWSwHCj-DPubbT_EmlbUsfagbBHCNQrOPUJCilkdOKcJNum9My4cXj8_aqtDGwM_pyNnxnpv_4qztBDPF5EbZsHzfhqNdaN09HHxoDW4DdclyYb__NpVNEQ8VOojYB-xmIhV2296BhrQlHGBKWXqf0hsDxjsTDrH2DoAVW3PvxLMrN_GMZXATVQFWHUgrd3oPGZYxgua5bs0mcPVFJujgbYR8SlHER6X5jb_3TnJbDWYowa0gzpQzr2dzW4RQxzjxGoD2dXgwZVZNIjj-X9y3NlCyxCxZmkaAa3jSiKRq6pYuRQNbfuMVU7nJZG5J_1BNGmvRWXhe9VJ6FH5lvPNfV1kyXj8EpSvgtYExSoXp5utKIiytVzXmZ6FwmoWYlI4WlofXnmRvDuC9dUeMpY9LuHI7zY-u3FSPvw2XuXaCPowy28u0RHIWhE9PE66pOoRWjwKpGblG7emXvDcvRNVw6YUCsJKiV2skEZbBw9P78DKyDWgBcbUNlqGngkxuPdPbIro0G_CjIO15iuw98TiQw7upmvzA1fiyc21prZbQ0y4AxaSYZDgMjzfuIA6vbw1F6O3pwOp1SrzU_Z9BK4caboU78mhcYO6bte926BUyTF0nA-9iIZld-BFfQXR-2GHsts2ltbuMkUBLf-1OTqKNocAL7vyHISKxqBL4BhVnxl2RjyoFP_luJuRx_MM2uRlLgtcQghc_K9gi80vwFgPi2Mfx2dpRTO2MT_io8QJmcIWjiDxo",
  "token_type" : "bearer",
  "expires_in" : 3599,
  "scope" : "checkout reporting thirdparty",
  "jti" : "3e0d485a-8433-47b4-b8c8-7e3f7571614b"
}

checkout_direct_sale = {
  "checkoutId" : "6be6a80d-ef67-47c8-a5bd-2461d11da24c",
  "type" : "DIRECT_SALE",
  "status" : "OPEN",
  "creationTimestamp" : "2017-10-02T08:41:09.728Z",
  "totalAmount" : 100.0,
  "shippingAmount" : 3.5,
  "orderAmount" : 96.5,
  "refundLimit" : 200,
  "currency" : "EUR",
  "items" : [ {
    "quantity" : 3,
    "name" : "Bobbycar",
    "ean" : "800001303",
    "price" : 25.99
  }, {
    "quantity" : 1,
    "name" : "Helm",
    "price" : 18.53
  } ],
  "deliveryType" : "STANDARD",
  "shippingAddress" : {
    "addresseeGivenName" : "Marie",
    "addresseeLastName" : "Mustermann",
    "company" : "Musterbau GmbH & Co KG",
    "street" : "Kastanienallee",
    "streetNr" : "999",
    "additionalAddressInformation" : "Im Rückgebäude",
    "zip" : "90402",
    "city" : "Schwaig",
    "countryCode" : "DE",
    "state" : "Bayern"
  },
  "merchantOrderReferenceNumber" : "order-A12223412",
  "merchantCustomerNumber" : "cust-732477",
  "merchantInvoiceReferenceNumber" : "20150112334345",
  "merchantReconciliationReferenceNumber" : "recon-A12223412",
  "note" : "Ihr Einkauf bei Spielauto-Versand.",
  "minimumAge" : 0,
  "redirectUrlAfterSuccess" : "https://spielauto-versand.de/order/123/success",
  "redirectUrlAfterCancellation" : "https://spielauto-versand.de/order/123/cancellation",
  "redirectUrlAfterAgeVerificationFailure" : "https://spielauto-versand.de/order/123/ageverificationfailed",
  "redirectUrlAfterRejection" : "https://spielauto-versand.de/order/123/rejection",
  "callbackUrlStatusUpdates" : "https://spielauto-versand.de/callback/status",
  "deliveryInformation" : {
    "expectedShippingDate" : "2016-10-19T12:00:00.000Z",
    "logisticsProvider" : "DHL",
    "trackingNumber" : "1234567890"
  },
  "_links" : {
    "approve" : {
      "href" : "https://paydirekt.de/checkout/#/checkout/6be6a80d-ef67-47c8-a5bd-2461d11da24c"
    },
    "self" : {
      "href" : "https://api.paydirekt.de/api/checkout/v1/checkouts/6be6a80d-ef67-47c8-a5bd-2461d11da24c"
    }
  }
}

checkout_order = {
  "checkoutId" : "dcc6cebc-5d92-4212-bca9-a442a32448e1",
  "type" : "ORDER",
  "status" : "OPEN",
  "creationTimestamp" : "2017-10-02T08:39:26.460Z",
  "totalAmount" : 100.0,
  "shippingAmount" : 2,
  "orderAmount" : 98,
  "refundLimit" : 110,
  "currency" : "EUR",
  "items" : [ {
    "quantity" : 3,
    "name" : "Bobbycar",
    "ean" : "800001303",
    "price" : 25.99
  }, {
    "quantity" : 1,
    "name" : "Helm",
    "price" : 18.53
  } ],
  "shoppingCartType" : "PHYSICAL",
  "deliveryType" : "STANDARD",
  "shippingAddress" : {
    "addresseeGivenName" : "Marie",
    "addresseeLastName" : "Mustermann",
    "company" : "Musterbau GmbH & Co KG",
    "street" : "Kastanienallee",
    "streetNr" : "999",
    "additionalAddressInformation" : "Im Rückgebäude",
    "zip" : "90402",
    "city" : "Schwaig",
    "countryCode" : "DE",
    "state" : "Bayern"
  },
  "merchantOrderReferenceNumber" : "order-A12223412",
  "merchantCustomerNumber" : "cust-732477",
  "merchantInvoiceReferenceNumber" : "20150112334345",
  "redirectUrlAfterSuccess" : "https://spielauto-versand.de/order/123/success",
  "redirectUrlAfterCancellation" : "https://spielauto-versand.de/order/123/cancellation",
  "redirectUrlAfterRejection" : "https://spielauto-versand.de/order/123/rejection",
  "callbackUrlStatusUpdates" : "https://spielauto-versand.de/callback/status",
  "_links" : {
    "approve" : {
      "href" : "https://paydirekt.de/checkout/#/checkout/dcc6cebc-5d92-4212-bca9-a442a32448e1"
    },
    "self" : {
      "href" : "https://api.paydirekt.de/api/checkout/v1/checkouts/dcc6cebc-5d92-4212-bca9-a442a32448e1"
    }
  }
}
capture_response = {
  "type" : "CAPTURE_ORDER",
  "transactionId" : "79cc2cdc-75ea-4496-9fd9-866b8b82dc39",
  "amount" : 10,
  "merchantReconciliationReferenceNumber" : "recon-1234",
  "finalCapture" : False,
  "merchantCaptureReferenceNumber" : "capture-21323",
  "captureInvoiceReferenceNumber" : "invoice-1234",
  "callbackUrlStatusUpdates" : "https://spielauto-versand.de/callback/status",
  "deliveryInformation" : {
    "expectedShippingDate" : "2016-10-19T12:00:00.000Z",
    "logisticsProvider" : "DHL",
    "trackingNumber" : "1234567890"
  },
  "status" : "SUCCESSFUL",
  "_links" : {
    "self" : {
      "href" : "https://api.paydirekt.de/api/checkout/v1/checkouts/f3fa56c8-5633-435b-96c2-60c343b315b7/captures/79cc2cdc-75ea-4496-9fd9-866b8b82dc39"
    }
  }
}

refund_response = {
  "type" : "REFUND",
  "transactionId" : "690bee3c-cbd2-4826-b883-0d85d25b1081",
  "amount" : 10,
  "merchantReconciliationReferenceNumber" : "recon-1234",
  "note" : "Ihre Bestellung vom 31.03.2015",
  "merchantRefundReferenceNumber" : "refund-21219",
  "status" : "PENDING",
  "reason" : "MERCHANT_CAN_NOT_DELIVER_GOODS",
  "callbackUrlStatusUpdates" : "https://spielauto-versand.de/callback/status",
  "_links" : {
    "self" : {
      "href" : "https://api.paydirekt.de/api/checkout/v1/checkouts/dcc6cebc-5d92-4212-bca9-a442a32448e1/refunds/690bee3c-cbd2-4826-b883-0d85d25b1081"
    }
  }
}

get_100_capture = {
  "type" : "CAPTURE_ORDER",
  "transactionId" : "79cc2cdc-75ea-4496-9fd9-866b8b82dc39",
  "amount" : 100,
  "merchantReconciliationReferenceNumber" : "recon-34",
  "finalCapture" : False,
  "merchantCaptureReferenceNumber" : "capture-2123",
  "captureInvoiceReferenceNumber" : "invoice-1234",
  "callbackUrlStatusUpdates" : "https://spielauto-versand.de/callback/status",
  "deliveryInformation" : {
    "expectedShippingDate" : "2016-10-19T12:00:00.000Z",
    "logisticsProvider" : "DHL",
    "trackingNumber" : "1234567890"
  },
  "status" : "SUCCESSFUL",
  "paymentInformationId" : "0000000-1111-2222-3333-949499202",
  "_links" : {
    "self" : {
      "href" : "https://api.paydirekt.de/api/checkout/v1/checkouts/f3fa56c8-5633-435b-96c2-60c343b315b7/captures/79cc2cdc-75ea-4496-9fd9-866b8b82dc39"
    }
  }
}

get_100_refund = {
  "type" : "REFUND",
  "transactionId" : "690bee3c-cbd2-4826-b883-0d85d25b1081",
  "amount" : 100,
  "merchantReconciliationReferenceNumber" : "recon-1234",
  "note" : "Ihre Bestellung vom 31.03.2015",
  "merchantRefundReferenceNumber" : "refund-99989",
  "status" : "PENDING",
  "reason" : "MERCHANT_CAN_NOT_DELIVER_GOODS",
  "callbackUrlStatusUpdates" : "https://spielauto-versand.de/callback/status",
  "paymentInformationId" : "0000000-1111-2222-3333-444444444444",
  "_links" : {
    "self" : {
      "href" : "https://api.paydirekt.de/api/checkout/v1/checkouts/dcc6cebc-5d92-4212-bca9-a442a32448e1/refunds/690bee3c-cbd2-4826-b883-0d85d25b1081"
    }
  }
}

Payment = create_test_payment(variant=VARIANT, currency='EUR', carttype=None)


class TestPaydirektProvider(TestCase):


    def test_direct_sale_response(self):
        payment = Payment(minimumage=0)
        provider = PaydirektProvider(API_KEY, SECRET)

        request = MagicMock()
        # real request (private data replaced) encountered, should not error and still be in waiting state
        request.body = json.dumps(sample_request_paydirekt)
        response = provider.process_data(payment, request)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(payment.status, PaymentStatus.WAITING)
        request.body = json.dumps(directsale_open_data)
        response = provider.process_data(payment, request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payment.status, PaymentStatus.WAITING)
        request.body = json.dumps(directsale_approve_data)
        response = provider.process_data(payment, request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payment.status, PaymentStatus.CONFIRMED)

    def test_order_response(self):
        payment = Payment(minimumage=0)
        provider = PaydirektProvider(API_KEY, SECRET, capture=False)

        request = MagicMock()
        request.body = json.dumps(order_open_data)
        response = provider.process_data(payment, request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payment.status, PaymentStatus.WAITING)
        request.body = json.dumps(order_approve_data)
        response = provider.process_data(payment, request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payment.status, PaymentStatus.PREAUTH)
        request.body = json.dumps(capture_process_data)
        response = provider.process_data(payment, request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payment.status, PaymentStatus.PREAUTH)
        request.body = json.dumps(order_close_data)
        response = provider.process_data(payment, request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payment.status, PaymentStatus.CONFIRMED)




    @patch("requests.post")
    def test_checkout_direct(self, mocked_post):
        payment = Payment(minimumage=0)
        provider = PaydirektProvider(API_KEY, SECRET, capture=False)
        def return_url_data(url, *args, **kwargs):
            response = MagicMock()
            response.status_code = 200
            if url == provider.path_token.format(provider.endpoint):
                response.text = json.dumps(token_retrieve)
            elif url == provider.path_checkout.format(provider.endpoint):
                response.text = json.dumps(checkout_direct_sale)
            else:
                raise
            return response
        mocked_post.side_effect = return_url_data
        with self.assertRaises(RedirectNeeded) as cm:
            provider.get_form(payment)
        self.assertEqual(cm.exception.args[0], "https://paydirekt.de/checkout/#/checkout/6be6a80d-ef67-47c8-a5bd-2461d11da24c")

    @patch("requests.post")
    def test_capture_refund(self, mocked_post):
        payment = Payment(minimumage=0)
        provider = PaydirektProvider(API_KEY, SECRET, capture=False)
        request = MagicMock()
        request.body = json.dumps(order_approve_data)
        provider.process_data(payment, request)

        def return_url_data(url, *args, **kwargs):
            response = MagicMock()
            response.status_code = 200
            if url == provider.path_token.format(provider.endpoint):
                response.text = json.dumps(token_retrieve)
            elif url == provider.path_capture.format(provider.endpoint, payment.transaction_id):
                response.text = json.dumps(capture_response)
            elif url == provider.path_refund.format(provider.endpoint, payment.transaction_id):
                response.text = json.dumps(refund_response)
            elif url == provider.path_close.format(provider.endpoint, payment.transaction_id):
                response.text = json.dumps(order_close_data)
            else:
                raise Exception(url)
            return response
        mocked_post.side_effect = return_url_data

        ret = provider.capture(payment)
        self.assertEqual(ret, Decimal(100))
        self.assertEqual(payment.status, PaymentStatus.PREAUTH)
        self.assertEqual(payment.captured_amount, Decimal("0.0"))

        payment.captured_amount = Decimal(100)
        ret = provider.refund(payment)
        self.assertEqual(ret, Decimal(100))
        self.assertEqual(payment.status, PaymentStatus.REFUNDED)
        self.assertEqual(payment.captured_amount, Decimal("100.0"))

    @patch("requests.post")
    @patch("requests.get")
    def test_refund_fail(self, mocked_get, mocked_post):
        payment = Payment(minimumage=0)
        provider = PaydirektProvider(API_KEY, SECRET, capture=False)
        def return_get_data(url, *args, **kwargs):
            response = MagicMock()
            response.status_code = 200
            response.text = json.dumps(get_100_refund)
            return response
        def return_post_data(url, *args, **kwargs):
            response = MagicMock()
            response.status_code = 200
            if url == provider.path_token.format(provider.endpoint):
                response.text = json.dumps(token_retrieve)
            else:
                raise
            return response
        mocked_get.side_effect = return_get_data
        mocked_post.side_effect = return_post_data
        request = MagicMock()
        request.body = json.dumps(order_approve_data)
        provider.process_data(payment, request)

        self.assertEqual(payment.status, PaymentStatus.PREAUTH)
        self.assertEqual(payment.captured_amount, Decimal(0))
        d = refund_process_data.copy()
        d["refundStatus"] = "FAILED"
        request.body = json.dumps(d)
        response = provider.process_data(payment, request)
        self.assertEqual(payment.captured_amount, Decimal(100))
        self.assertEqual(payment.status, PaymentStatus.ERROR)

    @patch("requests.post")
    @patch("requests.get")
    def test_capture_fail(self, mocked_get, mocked_post):
        payment = Payment(minimumage=0, captured_amount=Decimal(100))
        provider = PaydirektProvider(API_KEY, SECRET, capture=False)
        def return_get_data(url, *args, **kwargs):
            response = MagicMock()
            response.status_code = 200
            response.text = json.dumps(get_100_capture)
            return response

        def return_post_data(url, *args, **kwargs):
            response = MagicMock()
            response.status_code = 200
            if url == provider.path_token.format(provider.endpoint):
                response.text = json.dumps(token_retrieve)
            else:
                raise
            return response
        mocked_get.side_effect = return_get_data
        mocked_post.side_effect = return_post_data
        request = MagicMock()
        request.body = json.dumps(order_approve_data)
        provider.process_data(payment, request)

        self.assertEqual(payment.status, PaymentStatus.PREAUTH)
        self.assertEqual(payment.captured_amount, Decimal(100))
        d = capture_process_data.copy()
        d["captureStatus"] = "FAILED"
        request.body = json.dumps(d)
        response = provider.process_data(payment, request)
        self.assertEqual(payment.captured_amount, Decimal(0))
        self.assertEqual(payment.status, PaymentStatus.ERROR)
