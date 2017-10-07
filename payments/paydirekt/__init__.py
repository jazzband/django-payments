""" paydirekt payment provider """


from __future__ import unicode_literals
try:
    # For Python 3.0 and later
    from urllib.error import URLError
    from urllib.parse import urlencode
except ImportError:
    # Fall back to Python 2's urllib2
    from urllib2 import URLError
    from urllib import urlencode

import uuid
from datetime import datetime, tzinfo, timedelta
from base64 import urlsafe_b64encode, urlsafe_b64decode
import os
import email.utils
import hmac
import simplejson as json
import time
import logging

import requests
from django.http import HttpResponseRedirect, HttpResponseForbidden, HttpResponse
from django.conf import settings

from .. import PaymentError, PaymentStatus, RedirectNeeded
from ..core import BasicProvider
from ..utils import extract_streetnr

logger = logging.getLogger(__name__)

class utctimezone(tzinfo):
    def __init__(self):
        pass

    def utcoffset(self, dt):
        return timedelta(0)

    def dst(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return "UTC"

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
                 overcapture=False, **kwargs):
        if not isinstance(secret, bytes):
            self.secret_b64 = secret.encode('utf-8')
        self.api_key = api_key
        self.endpoint = endpoint
        self.overcapture = overcapture
        super(PaydirektProvider, self).__init__(**kwargs)

    def retrieve_oauth_token(self):
        """ Retrieves oauth Token and save it as instance variable """
        token_uuid = str(uuid.uuid4()).encode("utf-8")
        nonce = urlsafe_b64encode(os.urandom(48))
        date_now = datetime.now(utctimezone)
        bytessign = token_uuid+b":"+date_now.strftime("%Y%m%d%H%M%S").encode('utf-8')+b":"+self.api_key.encode('utf-8')+b":"+nonce
        h_temp = hmac.new(urlsafe_b64decode(self.secret_b64), msg=bytessign, digestmod='sha256')

        header = PaydirektProvider.header_default.copy()
        header["X-Auth-Key"] = self.api_key
        header["X-Request-ID"] = token_uuid

        header["X-Auth-Code"] = str(urlsafe_b64encode(h_temp.digest()), 'ascii')
        header["Date"] = email.utils.format_datetime(date_now, usegmt=True)
        body = {
            "grantType" : "api_key",
            "randomNonce" : str(nonce, "ascii")
        }
        response = requests.post(self.path_token.format(self.endpoint), data=json.dumps(body, use_decimal=True), headers=header)
        token_raw = json.loads(response.text, use_decimal=True)
        check_response(response, token_raw)

        self.access_token = token_raw["access_token"]
        self.expires_in = date_now+timedelta(seconds=token_raw["expires_in"])

    def check_and_update_token(self):
        """ Check if token exists or has expired, renew it in this case """
        if not self.expires_in or self.expires_in >= datetime.now(timezone.utc):
            self.retrieve_oauth_token()

    def get_form(self, payment, data=None):
        if not payment.id:
            payment.save()
        self.check_and_update_token()
        headers = PaydirektProvider.header_default.copy()
        headers["Authorization"] = "Bearer %s" % self.access_token
        # email_hash = sha256(payment.billing_email.encode("utf-8")).digest())
        body = {
            "type": "ORDER" if not self._capture else "DIRECT_SALE",
            "totalAmount": payment.total,
            "shippingAmount": payment.delivery,
            "orderAmount": payment.total - payment.delivery,
            "currency": payment.currency,
            #"items": getattr(payment, "items", None),
            #"shoppingCartType": getattr(payment, "carttype", None),
            #"deliveryType": getattr(payment, "deliverytype", None),
            # payment id can repeat if different shop systems are used
            "merchantOrderReferenceNumber": "%s:%s" % (hex(int(time.time())), payment.id),
            "redirectUrlAfterSuccess": payment.get_success_url(),
            "redirectUrlAfterCancellation": payment.get_failure_url(),
            "redirectUrlAfterRejection": payment.get_failure_url(),
            "callbackUrlStatusUpdates": self.get_return_url(payment),
            #"sha256hashedEmailAddress": str(urlsafe_b64encode(email_hash), 'ascii'),
            "minimumAge": getattr(payment, "minimumage", None),
            "redirectUrlAfterAgeVerificationFailure": payment.get_failure_url(),
            #"note": payment.message[0:37]

        }
        if self.overcapture and body["type"] == "ORDER":
            body["overcapture"] = True

        shipping = payment.get_shipping_address()

        shipping = {
            "addresseeGivenName": shipping["first_name"],
            "addresseeLastName": shipping["last_name"],
            "company": shipping.get("company", None),
            #"additionalAddressInformation": shipping["address_2"],
            "street": shipping["address_1"],
            "streetNr": extract_streetnr(shipping["address_1"], "0"),
            "zip": shipping["postcode"],
            "city": shipping["city"],
            "countryCode": shipping["country_code"],
            "state": shipping["country_area"],
            "emailAddress": payment.billing_email
        }
        #strip zeroes
        shipping = {k: v for k, v in shipping.items() if v}
        body = {k: v for k, v in body.items() if v}

        body["shippingAddress"] = shipping

        response = requests.post(self.path_checkout.format(self.endpoint), data=json.dumps(body, use_decimal=True), headers=headers)
        json_response = json.loads(response.text, use_decimal=True)
        check_response(response, json_response)
        raise RedirectNeeded(json_response["_links"]["approve"]["href"])

    def process_data(self, payment, request):
        try:
            results = json.loads(request.body, use_decimal=True)
        except (ValueError, TypeError):
            logger.error("paydirekt returned unparseable object")
            return HttpResponseForbidden('FAILED')
        if not payment.transaction_id:
            payment.transaction_id = results["checkoutId"]
        if results["checkoutStatus"] == "APPROVED":
            if self._capture:
                payment.change_status(PaymentStatus.CONFIRMED)
            else:
                payment.change_status(PaymentStatus.PREAUTH)
        else:
            payment.change_status(self.translate_status[results["checkoutStatus"]])
        payment.save()
        return HttpResponse('OK')

    def capture(self, payment, amount=None, final=True):
        if not amount:
            amount = payment.total
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
        if final:
            response = requests.post(self.path_close.format(self.endpoint, payment.transaction_id), \
                                     headers=header)
            json_response = json.loads(response.text, use_decimal=True)
            check_response(response, json_response)
        return amount

    def refund(self, payment, amount=None):
        if not amount:
            amount = payment.total
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
        return amount
