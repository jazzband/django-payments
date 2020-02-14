import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin

from django import forms
from django.http.response import HttpResponse, HttpResponseRedirect
from django.utils.html import format_html

import requests

from .. import PaymentStatus, RedirectNeeded
from ..core import BasicProvider, get_base_url
from ..forms import PaymentForm


sig_sorted_key_list = [
    "currency-code",
    "customer-email",
    "customer-language",
    "cvv-url",
    "merchant-pos-id",
    "payu-brand",
    "recurring-payment",
    "shop-name",
    "store-card",
    "total-amount",
    "widget-mode",
]

CURRENCY_SUB_UNIT = {
    'PLN': Decimal(100),
    'EUR': Decimal(100),
    'USD': Decimal(100),
    'CZK': Decimal(100),
    'GBP': Decimal(100),
}


CENTS = Decimal('0.01')


def quantize_price(price):
    return price.quantize(CENTS, rounding=ROUND_HALF_UP)


# A bit hacky method, how to get PayU javascript into the form
class ScriptField(forms.HiddenInput):
    def __init__(self, script_params, payment, *args, **kwargs):
        self.script_params = script_params
        self.payment = payment
        return super(ScriptField, self).__init__(*args, **kwargs)

    def render(self, name, value, script_params={}, attrs=None, renderer=None):
        super(ScriptField, self).render(name, value, attrs)
        inline_code = format_html(
            "<script "
            "src='https://secure.snd.payu.com/front/widget/js/payu-bootstrap.js' "
            "pay-button='#pay-button' {} >"
            "</script>",
            " ".join('%s=%s' % (k, v) for k, v in self.script_params.items()),
        )

        return inline_code + """
            <script>
                function cardSuccess($data) {
                    console.log('callback');
                    console.log($data);
                    $.post(
                        '%s',
                        $data,
                        function(data){ window.location.href=data; }
                    );
                }
                function cvvSuccess($data) {
                    console.log('cvv success');
                    console.log($data);
                    window.location.href="%s";
                }
            </script>
            <div id="payu-widget"></div>
            """ % (
            urljoin(
                get_base_url(),
                self.payment.get_process_url(),
            ),
            urljoin(
                get_base_url(),
                self.payment.get_success_url(),
            ),
        )


class WidgetPaymentForm(PaymentForm):
    hide_submit_button = True  # For easy use in templates
    script = forms.CharField(label="Script")

    def __init__(self, script_params={}, *args, **kwargs):
        ret = super(WidgetPaymentForm, self).__init__(*args, **kwargs)
        self.fields['script'].widget = ScriptField(
            script_params=script_params,
            payment=self.payment,
        )
        return ret


class RenewPaymentForm(PaymentForm):
    confirm = forms.BooleanField(label="Renew the payment", required=True)

    def __init__(self, *args, **kwargs):
        ret = super(RenewPaymentForm, self).__init__(*args, **kwargs)
        self.action = urljoin(get_base_url(), self.payment.get_process_url())
        return ret


class PayuApiError(Exception):
    pass


class PayuProvider(BasicProvider):

    def __init__(self, *args, **kwargs):
        self.client_secret = kwargs.pop('client_secret')
        self.second_key = kwargs.pop('second_key')
        self.payu_sandbox = kwargs.pop("sandbox", False)
        self.payu_base_url = kwargs.pop(
            "base_payu_url",
            "https://secure.snd.payu.com/" if self.payu_sandbox else "https://secure.payu.com/",
        )
        self.payu_auth_url = kwargs.pop('auth_url', urljoin(self.payu_base_url, "/pl/standard/user/oauth/authorize"))
        self.payu_api_url = kwargs.pop('api_url', urljoin(self.payu_base_url, 'api/v2_1/'))
        self.payu_token_url = kwargs.pop('token_url', urljoin(self.payu_api_url, 'tokens/'))
        self.payu_api_order_url = urljoin(self.payu_api_url, "orders/")
        self.payu_api_paymethods_url = urljoin(self.payu_api_url, "paymethods/")
        self.payu_widget_branding = kwargs.pop('widget_branding', False)
        self.grant_type = kwargs.pop('grant_type', 'client_credentials')
        self.recurring_payments = kwargs.pop('recurring_payments', False)

        # Use card on file paremeter instead of recurring. PayU asks CVV2 every time with this setting which can be used for testing purposes.
        self.card_on_file = kwargs.pop('card_on_file', False)

        self.express_payments = kwargs.pop('express_payments', False)
        self.retry_count = 5

        self.pos_id = kwargs.pop('pos_id')
        self.token = self.get_access_token(self.pos_id, self.client_secret, grant_type=self.grant_type)
        super(PayuProvider, self).__init__(*args, **kwargs)

    def get_sig(self, payu_data):
        string = "".join(str(payu_data[key]) for key in sig_sorted_key_list if key in payu_data)
        string += self.second_key
        return hashlib.sha256(string.encode('utf-8')).hexdigest().lower()

    def auto_complete_recurring(self, payment):
        renew_token = payment.get_renew_token()
        url = self.process_widget(payment, renew_token, recurring="STANDARD", auto_renew=True)
        if not url.startswith("http") and url != 'success':
            url = urljoin(get_base_url(), url)
        return url

    def get_form(self, payment, data={}):
        if not data:
            data = {}

        if not self.express_payments:
            pay_link = self.create_order(payment, self.get_processor(payment))
            raise RedirectNeeded(pay_link)

        cvv_url = None
        if payment.extra_data:
            extra_data = json.loads(payment.extra_data)
            if 'cvv_url' in extra_data:
                cvv_url = extra_data['cvv_url']

        renew_token = payment.get_renew_token()
        if renew_token and self.recurring_payments and not cvv_url:
            return RenewPaymentForm(provider=self, payment=payment)
            # Use this, if the user doesn't need to be informed about the recurring payment:
            # raise RedirectNeeded(payment.get_process_url())

        payu_data = {
            "merchant-pos-id": self.pos_id,
            "shop-name": " ".join((payment.billing_first_name, payment.billing_last_name)).strip().replace(" ", "_"),
            "total-amount": payment.total,
            "currency-code": payment.currency,
            "customer-language": "en",
            "success-callback": "cardSuccess",
        }
        if cvv_url:
            payu_data.update({
                'cvv-url': cvv_url,
                'cvv-success-callback': 'cvvSuccess',
                'widget-type': 'cvv'
            })
        else:
            payu_data.update({
                "customer-email": payment.get_user_email(),
                "store-card": "true",
                "payu-brand": str(self.payu_widget_branding).lower(),
            })
            if self.recurring_payments:
                payu_data["recurring-payment"] = "true"
        payu_data['sig'] = self.get_sig(payu_data)
        return WidgetPaymentForm(data=data, script_params=payu_data, provider=self, payment=payment)

    def get_processor(self, payment):
        order = payment.get_purchased_items()
        notify_url = urljoin(get_base_url(), payment.get_process_url())
        processor = PaymentProcessor(
            order=order,
            notify_url=notify_url,
            currency=payment.currency,
            description=payment.description,
            customer_ip=payment.customer_ip_address,
            total=payment.total,
        )
        processor.set_buyer_data(
            first_name=payment.get_user_first_name(),
            last_name=payment.get_user_last_name(),
            email=payment.get_user_email(),
            phone=None,
        )
        processor.external_id = payment.token
        processor.continueUrl = urljoin(get_base_url(), payment.get_success_url())
        return processor

    def process_widget(self, payment, card_token, recurring="FIRST", auto_renew=False):
        processor = self.get_processor(payment)
        if self.card_on_file:
            processor.cardOnFile = 'FIRST' if recurring == 'FIRST' else 'STANDARD_CARDHOLDER'
        elif self.recurring_payments:
            processor.recurring = recurring
        if self.express_payments:
            processor.set_paymethod(method_type="CARD_TOKEN", value=card_token)
        data = self.create_order(payment, processor, auto_renew)
        return data

    def process_widget_callback(self, payment, card_token, recurring="FIRST"):
        data = self.process_widget(payment, card_token, recurring)
        if recurring == "STANDARD":
            return HttpResponseRedirect(data)
        return HttpResponse(data, status=200)

    def post_request(self, url, *args, **kwargs):
        if 'headers' not in kwargs:
            kwargs['headers'] = self.get_token_headers()
        for i in range(1, self.retry_count):
            response = requests.post(url, *args, **kwargs)
            response_dict = json.loads(response.text)
            if 'status' in response_dict and 'statusCode' in response_dict['status'] and response_dict['status']['statusCode'] == 'UNAUTHORIZED':
                try:
                    self.token = self.get_access_token(self.pos_id, self.client_secret, grant_type=self.grant_type)
                except PayuApiError:
                    pass
            else:
                return response_dict
        raise PayuApiError("Unable to regain authorization token")

    def get_access_token(self, client_id, client_secret, grant_type='client_credentials', email=None, customer_id=None):
        """
        Get access token from PayU API
        grant_type: 'trusted_merchant' or 'client_credentials'
        email and customer_id is required only for grant_type=trusted_merchant
        """

        payu_auth_url = self.payu_auth_url
        data = {
            'grant_type': grant_type,
            'client_id': client_id,
            'client_secret': client_secret,
        }
        if email:
            data['email'] = email
        if customer_id:
            data['ext_customer_id'] = customer_id

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        response = requests.post(payu_auth_url, data=data, headers=headers)
        response_dict = json.loads(response.text)

        try:
            return response_dict['access_token']
        except (KeyError, ValueError):
            raise PayuApiError(response_dict)

    def get_token_headers(self):
        return {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % self.token,
        }

    def delete_card_token(self, card_token):
        "Deactivate card token on PayU"

        payu_delete_token_url = urljoin(self.payu_token_url, card_token)
        response = requests.delete(payu_delete_token_url, headers=self.get_token_headers())
        self.token = None

        return (response.status_code == 204)

    def create_order(self, payment, payment_processor, auto_renew=False):
        """
        Create order and return payment link or redirect

        return redirectUrl  url where the user should go next
        """
        payment_processor.pos_id = self.pos_id
        response_dict = self.post_request(
            self.payu_api_order_url,
            data=payment_processor.as_json(),
            allow_redirects=False,
        )

        try:
            payment.transaction_id = response_dict['orderId']

            if response_dict['status']['statusCode'] == u'SUCCESS':
                if 'payMethods' in response_dict:
                    payment.set_renew_token(
                        response_dict['payMethods']['payMethod']['value'],
                        card_expire_year=response_dict['payMethods']['payMethod']['card']['expirationYear'],
                        card_expire_month=response_dict['payMethods']['payMethod']['card']['expirationMonth'],
                    )
                payment.extra_data = json.dumps({'card_response': response_dict}, indent=2)
                payment.save()
                if 'redirectUri' in response_dict:
                    payment.pay_link = response_dict['redirectUri']
                    payment.save()
                    return response_dict['redirectUri']
                else:
                    if auto_renew:
                        return "success"
                    return payment_processor.continueUrl
            elif response_dict['status']['statusCode'] == u'WARNING_CONTINUE_CVV':
                payment.extra_data = json.dumps({'cvv_url': response_dict['redirectUri']}, indent=2)
                payment.save()
                return payment.get_payment_url()
            elif response_dict['status']['statusCode'] == u'WARNING_CONTINUE_3DS':
                return response_dict['redirectUri']
        except KeyError:
            pass

        raise PayuApiError(response_dict)

    # Method that returns all pay methods

    def get_paymethod_tokens(self):
        "Get pay methods of POS, if authenticated with 'trusted_merchant' grant type, it will get also card tokens"

        response = requests.get(self.payu_api_paymethods_url, headers=self.get_token_headers())
        response_dict = json.loads(response.text)
        return response_dict

    # Method that rejects the order

    def reject_order(self, payment):
        "Reject order"

        url = urljoin(
            self.payu_api_order_url,
            payment.transaction_id,
        )

        try:
            # If the payment have status WAITING_FOR_CONFIRMATION, it is needed to make two calls of DELETE
            # http://developers.payu.com/pl/restapi.html#cancellation
            response1 = json.loads(requests.delete(url, headers=self.get_token_headers()).text)
            response2 = json.loads(requests.delete(url, headers=self.get_token_headers()).text)

            if response1['status']['statusCode'] == response2['status']['statusCode'] == 'SUCCESS':
                payment.change_status(PaymentStatus.REJECTED)
                return True
            else:
                raise PayuApiError(response1, response2)
        except PayuApiError:
            return False

    def process_notification(self, payment, request):
        try:
            json.loads(request.body.decode("utf8"))
            header = request.META['HTTP_OPENPAYU_SIGNATURE']
        except KeyError:
            raise PayuApiError('Malformed POST')

        header_data_raw = header.split(';')
        header_data = {}
        for x in header_data_raw:
            key, value = x.split('=')[0], x.split('=')[1]
            header_data[key] = value

        incoming_signature = header_data['signature']
        algorithm = header_data['algorithm']

        if algorithm == 'MD5':
            m = hashlib.md5()
            key = self.second_key
            signature = request.body + key.encode("utf8")
            m.update(signature)
            signature = m.hexdigest()
            if incoming_signature == signature:  # and not payment.status == PaymentStatus.CONFIRMED:
                data = json.loads(request.body.decode("utf8"))
                status = data['order']['status']
                status_map = {
                    'COMPLETED': PaymentStatus.CONFIRMED,
                    'PENDING': PaymentStatus.WAITING,
                    'WAITING_FOR_CONFIRMATION': PaymentStatus.WAITING,
                    'CANCELED': PaymentStatus.REJECTED,
                    'NEW': '',
                }
                payment.change_status(status_map[status])
                return HttpResponse("ok", status=200)
        return HttpResponse("not ok", status=500)

    def process_data(self, payment, request, *args, **kwargs):
        self.request = request

        renew_token = payment.get_renew_token()

        if 'application/json' in request.META.get('CONTENT_TYPE', {}):
            return self.process_notification(payment, request)
        elif renew_token and self.recurring_payments:
            return self.process_widget_callback(payment, renew_token, recurring="STANDARD")
        elif 'value' in request.POST:
            return self.process_widget_callback(payment, request.POST.get('value'), recurring="FIRST")


class PaymentProcessor(object):
    "Payment processor"

    def __init__(self, order, notify_url, currency, description, customer_ip, **kwargs):
        self.order = order
        self.notify_url = notify_url
        self.currency = currency
        self.description = description
        self.customer_ip = customer_ip
        self.order_items = []
        self.external_id = None
        self.pos_id = None
        self.total = None

    def get_order_items(self):
        for purchased_item in self.order:
            item = {
                'name': purchased_item.name[:127],
                'quantity': purchased_item.quantity,
                'unitPrice': purchased_item.price,
                'currency': purchased_item.currency,
            }
            yield item

    def set_paymethod(self, value, method_type="PBL"):
        "Set payment method, can given by PayuApi.get_paymethod_tokens()"
        if not hasattr(self, 'paymethods'):
            self.paymethods = {}
            self.paymethods['payMethod'] = {'type': method_type, 'value': value}

    def set_buyer_data(self, first_name, last_name, email, phone, lang_code='en'):
        "Set buyer data"
        if not hasattr(self, 'buyer'):
            self.buyer = {
                'email': email,
                'phone': phone,
                'firstName': first_name,
                'lastName': last_name,
                'language': lang_code
            }

    def as_json(self):
        "Return json for the payment"
        total = 0
        products = []
        order_items = self.get_order_items()
        for i in order_items:
            total += i['unitPrice'] * i['quantity']
            i['subUnit'] = int(quantize_price(CURRENCY_SUB_UNIT[self.currency]))
            i['unitPrice'] = int(quantize_price(i['unitPrice']))
            products.append(i)

        self.total = int(quantize_price((total * CURRENCY_SUB_UNIT[self.currency])))

        json_dict = {
            'notifyUrl': self.notify_url,
            'customerIp': self.customer_ip,
            # 'extOrderId': self.external_id,
            # NOTE: extOrderId prevents the payment from being submitted twice, which generates error,
            # that is can't be easily displayed to user, so we left it blank.
            'merchantPosId': self.pos_id,
            'description': self.description,
            'currencyCode': self.currency,
            'totalAmount': self.total,
            'products': products,
        }

        # additional data
        if hasattr(self, 'paymethods'):
            json_dict['payMethods'] = self.paymethods

        if hasattr(self, 'buyer'):
            json_dict['buyer'] = self.buyer

        if hasattr(self, 'continueUrl'):
            json_dict['continueUrl'] = self.continueUrl

        if hasattr(self, 'validityTime'):
            json_dict['validityTime'] = self.validityTime

        if hasattr(self, 'recurring'):
            json_dict['recurring'] = self.recurring

        if hasattr(self, 'cardOnFile'):
            json_dict['cardOnFile'] = self.cardOnFile

        return json.dumps(json_dict)
