""" paydirekt payment provider """

from __future__ import unicode_literals
import six
if six.PY3:
    # For Python 3.0 and later
    from urllib.error import URLError
    from urllib.parse import urlencode
else:
    # Fall back to Python 2's urllib2
    from urllib2 import URLError
    from urllib import urlencode

import uuid
from datetime import timedelta
from datetime import datetime as dt

from decimal import Decimal
from base64 import urlsafe_b64encode, urlsafe_b64decode
import os
import hmac
# for hmac and hashed email
import hashlib
import simplejson as json
import time
import logging
import threading

import requests
from django.http import HttpResponseRedirect, HttpResponseForbidden, HttpResponseServerError, HttpResponse
from django.conf import settings

from .. import PaymentError, PaymentStatus, RedirectNeeded
from ..core import BasicProvider
from ..utils import extract_streetnr

logger = logging.getLogger(__name__)

# from email utils, for python 2+3 support
def format_timetuple_and_zone(timetuple, zone):
    return '%s, %02d %s %04d %02d:%02d:%02d %s' % (
        ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][timetuple[6]],
        timetuple[2],
        ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
         'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][timetuple[1] - 1],
        timetuple[0], timetuple[3], timetuple[4], timetuple[5],
zone)

def check_response(response, response_json=None):
    if response.status_code not in [200, 201]:
        if response_json:
            try:
                errorcode = response_json["messages"][0]["code"] if "messages" in response_json and len(response_json["messages"]) > 0 else None
                raise PaymentError("{}\n--------------------\n{}".format(response.status_code, response_json), code=errorcode)
            except KeyError:
                raise PaymentError(str(response.status_code))
        else:
            raise PaymentError(str(response.status_code))

# Capture: if False ORDER is used
class PaydirektProvider(BasicProvider):
    '''
    paydirekt payment provider

    api_key:
        seller key, assigned by paydirekt
    secret:
        seller secret key (=encoded in base64)
    endpoint:
        which endpoint to use
    '''
    access_token = None
    expires_in = None

    path_token = "{}/api/merchantintegration/v1/token/obtain"
    path_checkout = "{}/api/checkout/v1/checkouts"
    path_capture = "{}/api/checkout/v1/checkouts/{}/captures"
    path_close = "{}/api/checkout/v1/checkouts/{}/close"
    path_refund = "{}/api/checkout/v1/checkouts/{}/refunds"


    translate_status = {
        "APPROVED": PaymentStatus.CONFIRMED,
        "OPEN": PaymentStatus.PREAUTH,
        "PENDING": PaymentStatus.WAITING,
        "REJECTED": PaymentStatus.REJECTED,
        "CANCELED": PaymentStatus.ERROR,
        "CLOSED": PaymentStatus.CONFIRMED,
        "EXPIRED": PaymentStatus.ERROR,
    }
    header_default = {
        "Content-Type": "application/hal+json;charset=utf-8",
    }


    def __init__(self, api_key, secret, endpoint="https://api.sandbox.paydirekt.de", \
                 overcapture=False, default_carttype="PHYSICAL", **kwargs):
        self.secret_b64 = secret.encode('utf-8')
        self.api_key = api_key
        self.endpoint = endpoint
        self.overcapture = overcapture
        self.default_carttype = default_carttype
        self.updating_token_lock = threading.Lock()
        super(PaydirektProvider, self).__init__(**kwargs)

    def retrieve_oauth_token(self):
        """ Retrieves oauth Token and save it as instance variable """
        token_uuid = str(uuid.uuid4()).encode("utf-8")
        nonce = urlsafe_b64encode(os.urandom(48))
        date_now = dt.utcnow()
        bytessign = token_uuid+b":"+date_now.strftime("%Y%m%d%H%M%S").encode('utf-8')+b":"+self.api_key.encode('utf-8')+b":"+nonce
        h_temp = hmac.new(urlsafe_b64decode(self.secret_b64), msg=bytessign, digestmod=hashlib.sha256)

        header = PaydirektProvider.header_default.copy()
        header["X-Auth-Key"] = self.api_key
        header["X-Request-ID"] = token_uuid

        if six.PY3:
            header["X-Auth-Code"] = str(urlsafe_b64encode(h_temp.digest()), 'ascii')
        else:
            header["X-Auth-Code"] = urlsafe_b64encode(h_temp.digest())
        header["Date"] = format_timetuple_and_zone(date_now.utctimetuple(), "GMT")
        body = {
            "grantType" : "api_key",
            "randomNonce" : str(nonce, "ascii") if six.PY3 else nonce
        }
        response = requests.post(self.path_token.format(self.endpoint), data=json.dumps(body, use_decimal=True), headers=header)
        token_raw = json.loads(response.text, use_decimal=True)
        check_response(response, token_raw)

        self.access_token = token_raw["access_token"]
        self.expires_in = date_now+timedelta(seconds=token_raw["expires_in"])

    def check_and_update_token(self):
        """ Check if token exists or has expired, renew it in this case """
        self.updating_token_lock.acquire()
        try:
            if not self.expires_in or self.expires_in >= dt.utcnow()-timedelta(seconds=3):
                self.retrieve_oauth_token()
        except Exception as exc:
            self.updating_token_lock.release()
            raise exc
        self.updating_token_lock.release()


    def _prepare_items(self, payment):
        items = []
        for newitem in payment.get_purchased_items():
            items.append({
                "name": newitem.name,
                # limit to 2 decimal_places even 4 decimal_places should be possible
                "price": newitem.price.quantize(Decimal('0.01')),
                "quantity": int(newitem.quantity)
            })
        return items

    def _retrieve_amount(self, url):
        ret = requests.get(url)
        try:
            results = json.loads(ret.text, use_decimal=True)
        except (ValueError, TypeError):
            logger.error("paydirekt returned unparseable object")
            return None
        return results.get("amount", None)

    def get_form(self, payment, data=None):
        if not payment.id:
            payment.save()
        self.check_and_update_token()
        headers = PaydirektProvider.header_default.copy()
        headers["Authorization"] = "Bearer %s" % self.access_token
        email_hash = hashlib.sha256(payment.billing_email.encode("utf-8")).digest()
        body = {
            "type": "ORDER" if not self._capture else "DIRECT_SALE",
            "totalAmount": payment.total,
            "shippingAmount": payment.delivery,
            "orderAmount": payment.total - payment.delivery,
            "currency": payment.currency,
            "refundLimit": 100,
            "shoppingCartType": getattr(payment, "carttype", self.default_carttype),
            # payment id can repeat if different shop systems are used
            "merchantOrderReferenceNumber": "%s:%s" % (hex(int(time.time()))[2:], payment.id),
            "redirectUrlAfterSuccess": payment.get_success_url(),
            "redirectUrlAfterCancellation": payment.get_failure_url(),
            "redirectUrlAfterRejection": payment.get_failure_url(),
            "redirectUrlAfterAgeVerificationFailure": payment.get_failure_url(),
            "callbackUrlStatusUpdates": self.get_return_url(payment),
            # email sent anyway (shipping)
            "sha256hashedEmailAddress": str(urlsafe_b64encode(email_hash), 'ascii'),
            "minimumAge": getattr(payment, "minimumage", None)
        }
        if body["type"] == "DIRECT_SALE":
            body["note"] = payment.description[:37]
        if self.overcapture and body["type"] in ["ORDER", "ORDER_SECURED"]:
            body["overcapture"] = True

        shipping = payment.get_shipping_address()

        shipping = {
            "addresseeGivenName": shipping["first_name"],
            "addresseeLastName": shipping["last_name"],
            "company": shipping.get("company", None),
            "additionalAddressInformation": shipping["address_2"],
            "street": shipping["address_1"],
            "streetNr": extract_streetnr(shipping["address_1"], "0"),
            "zip": shipping["postcode"],
            "city": shipping["city"],
            "countryCode": shipping["country_code"],
            "state": shipping["country_area"],
            "emailAddress": payment.billing_email
        }
        #strip Nones
        shipping = {k: v for k, v in shipping.items() if v}
        body = {k: v for k, v in body.items() if v}

        body["shippingAddress"] = shipping

        items = self._prepare_items(payment)
        if len(items) > 0:
            body["items"] = items

        response = requests.post(self.path_checkout.format(self.endpoint), data=json.dumps(body, use_decimal=True), headers=headers)
        json_response = json.loads(response.text, use_decimal=True)

        check_response(response, json_response)
        payment.transaction_id = json_response["checkoutId"]
        payment.save()
        raise RedirectNeeded(json_response["_links"]["approve"]["href"])

    def process_data(self, payment, request):
        try:
            results = json.loads(request.body, use_decimal=True)
        except (ValueError, TypeError):
            logger.error("paydirekt returned unparseable object")
            return HttpResponseForbidden('FAILED')
        if not payment.transaction_id:
            # delay
            if not "checkoutId" in results:
                return HttpResponseServerError('no transaction_id')
            payment.transaction_id = results["checkoutId"]
            payment.save()
        if "checkoutStatus" in results:
            if results["checkoutStatus"] == "APPROVED":
                if self._capture:
                    payment.change_status(PaymentStatus.CONFIRMED)
                else:
                    payment.change_status(PaymentStatus.PREAUTH)
            elif results["checkoutStatus"] == "CLOSED":
                if payment.status != PaymentStatus.REFUNDED:
                    payment.change_status(PaymentStatus.CONFIRMED)
                elif payment.status == PaymentStatus.PREAUTH and payment.captured_amount == 0:
                    payment.change_status(PaymentStatus.REFUNDED)
            elif not results["checkoutStatus"] in ["OPEN", "PENDING"]:
                payment.change_status(PaymentStatus.ERROR)
        elif "refundStatus" in results:
            if results["refundStatus"] == "FAILED":
                logger.error("refund failed, try to recover")
                amount = self._retrieve_amount("/".join([self.path_refund.format(self.endpoint, payment.transaction_id), results["transactionId"]]))
                if not amount:
                    logger.error("refund recovery failed")
                    payment.change_status(PaymentStatus.ERROR)
                    return HttpResponseForbidden('FAILED')
                logger.error("refund recovery successfull")
                payment.captured_amount += amount
                payment.save()
                payment.change_status(PaymentStatus.ERROR)
        elif "captureStatus" in results:
            # e.g. if not enough money or capture limit reached
            if results["captureStatus"] == "FAILED":
                logger.error("capture failed, try to recover")
                amount = self._retrieve_amount("/".join([self.path_capture.format(self.endpoint, payment.transaction_id), results["transactionId"]]))
                if not amount:
                    logger.error("capture recovery failed")
                    payment.change_status(PaymentStatus.ERROR)
                    return HttpResponseForbidden('FAILED')
                logger.error("capture recovery successfull")
                payment.captured_amount -= amount
                payment.save()
                payment.change_status(PaymentStatus.ERROR)
        payment.save()
        return HttpResponse('OK')

    def capture(self, payment, amount=None, final=True):
        if not amount:
            amount = payment.total
        if not amount: raise Exception(self.total)
        if self.overcapture and amount > payment.total*Decimal("1.1"):
            return None
        elif not self.overcapture and amount > payment.total:
            return None
        self.check_and_update_token()
        header = PaydirektProvider.header_default.copy()
        header["Authorization"] = "Bearer %s" % self.access_token
        body = {
            "amount": amount,
            "finalCapture": final,
            "callbackUrlStatusUpdates": self.get_return_url(payment)
        }
        response = requests.post(self.path_capture.format(self.endpoint, payment.transaction_id), \
                                 data=json.dumps(body, use_decimal=True), headers=header)
        json_response = json.loads(response.text, use_decimal=True)
        check_response(response, json_response)
        return amount

    def refund(self, payment, amount=None):
        if not amount:
            amount = payment.captured_amount
        self.check_and_update_token()
        header = PaydirektProvider.header_default.copy()
        header["Authorization"] = "Bearer %s" % self.access_token
        body = {
            "amount": amount,
            "callbackUrlStatusUpdates": self.get_return_url(payment)
        }
        response = requests.post(self.path_refund.format(self.endpoint, payment.transaction_id), \
                                 data=json.dumps(body, use_decimal=True), headers=header)
        json_response = json.loads(response.text, use_decimal=True)
        check_response(response, json_response)
        if payment.status == PaymentStatus.PREAUTH and amount == payment.captured_amount:
            # logic, elsewise multiple signals are emitted CONFIRMED -> REFUNDED
            payment.change_status(PaymentStatus.REFUNDED)
            self.check_and_update_token()
            response = requests.post(self.path_close.format(self.endpoint, payment.transaction_id), \
                                 headers=header)
            json_response = json.loads(response.text, use_decimal=True)
            check_response(response, json_response)
        return amount
