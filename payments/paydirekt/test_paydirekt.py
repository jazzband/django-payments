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

directsale_data = {
  "checkoutId" : "6be6a80d-ef67-47c8-a5bd-2461d11da24c",
  "merchantOrderReferenceNumber" : "order-A12223412",
  "checkoutStatus" : "APPROVED"
}

order_data = {
  "checkoutId" : "dcc6cebc-5d92-4212-bca9-a442a32448e1",
  "merchantOrderReferenceNumber" : "order-A12223412",
  "checkoutStatus" : "APPROVED"
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
  "minimumAge" : 18,
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
  "merchantRefundReferenceNumber" : "refund-99989",
  "status" : "PENDING",
  "reason" : "MERCHANT_CAN_NOT_DELIVER_GOODS",
  "callbackUrlStatusUpdates" : "https://spielauto-versand.de/callback/status",
  "_links" : {
    "self" : {
      "href" : "https://api.paydirekt.de/api/checkout/v1/checkouts/dcc6cebc-5d92-4212-bca9-a442a32448e1/refunds/690bee3c-cbd2-4826-b883-0d85d25b1081"
    }
  }
}


Payment = create_test_payment(variant=VARIANT, currency='EUR')


class TestPaydirektProvider(TestCase):

    def setUp(self):
        self.payment = Payment(minimumage=0)
        self.provider = PaydirektProvider(API_KEY, SECRET)

    def test_process_data(self):
        request = MagicMock()
        request.body = json.dumps(directsale_data)
        response = self.provider.process_data(self.payment, request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)

    @patch("requests.post")
    def test_checkout_direct(self, mocked_post):
        def return_url_data(url, *args, **kwargs):
            response = MagicMock()
            response.status_code = 200
            if url == self.provider.path_token.format(self.provider.endpoint):
                response.text = json.dumps(token_retrieve)
            elif url == self.provider.path_checkout.format(self.provider.endpoint):
                response.text = json.dumps(checkout_direct_sale)
            else:
                raise
            return response
        mocked_post.side_effect = return_url_data
        with self.assertRaises(RedirectNeeded) as cm:
            self.provider.get_form(self.payment)
        self.assertEqual(cm.exception.args[0], "https://paydirekt.de/checkout/#/checkout/6be6a80d-ef67-47c8-a5bd-2461d11da24c")

    @patch("requests.post")
    def test_checkout_order(self, mocked_post):
        def return_url_data(url, *args, **kwargs):
            response = MagicMock()
            response.status_code = 200
            if url == self.provider.path_token.format(self.provider.endpoint):
                response.text = json.dumps(token_retrieve)
            elif url == self.provider.path_checkout.format(self.provider.endpoint):
                response.text = json.dumps(checkout_order)
            else:
                raise
            return response
        mocked_post.side_effect = return_url_data

        with self.assertRaises(RedirectNeeded) as cm:
            self.provider.get_form(self.payment)
        self.assertEqual(cm.exception.args[0], "https://paydirekt.de/checkout/#/checkout/dcc6cebc-5d92-4212-bca9-a442a32448e1")

    @patch("requests.post")
    def test_capture_refund(self, mocked_post):
        request = MagicMock()
        request.body = json.dumps(order_data)
        self.provider.process_data(self.payment, request)

        def return_url_data(url, *args, **kwargs):
            response = MagicMock()
            response.status_code = 200
            if url == self.provider.path_token.format(self.provider.endpoint):
                response.text = json.dumps(token_retrieve)
            elif url == self.provider.path_capture.format(self.provider.endpoint, self.payment.transaction_id):
                response.text = json.dumps(capture_response)
            elif url == self.provider.path_refund.format(self.provider.endpoint, self.payment.transaction_id):
                response.text = json.dumps(refund_response)
            else:
                raise
            return response
        mocked_post.side_effect = return_url_data

        ret = self.provider.capture(self.payment)
        self.assertEqual(ret, Decimal(100))
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
        self.assertEqual(self.payment.captured_amount, Decimal("0.0"))

        ret = self.provider.refund(self.payment)
        self.assertEqual(ret, Decimal(100))
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
        self.assertEqual(self.payment.captured_amount, Decimal("0.0"))
