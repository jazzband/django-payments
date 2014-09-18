from __future__ import unicode_literals
import datetime
import os.path

from django.core import signing
from django.shortcuts import redirect
from django.utils.translation import ugettext as _
import suds.client
from suds.sax.element import Element
from suds.sudsobject import Object
import suds.wsse

from .forms import PaymentForm
from .. import (
    BasicProvider, ExternalPostNeeded, get_credit_card_issuer, PaymentError,
    RedirectNeeded)
from ..forms import PaymentForm as BaseForm


ACCEPTED = 100
TRANSACTION_SETTLED = 238
TRANSACTION_REVERSED = 237
AUTHENTICATE_REQUIRED = 475

FRAUD_MANAGER_REVIEW = 480
FRAUD_MANAGER_REJECT = 481
FRAUD_SCORE_EXCEEDS_THRESHOLD = 400

# Soft Decline
ADDRESS_VERIFICATION_SERVICE_FAIL = 200
CARD_VERIFICATION_NUMBER_FAIL = 230
SMART_AUTHORIZATION_FAIL = 520


class CyberSourceProvider(BasicProvider):
    '''CyberSource payment provider
    '''

    fingerprint_url = 'https://h.online-metrix.net/fp/'

    def __init__(self, *args, **kwargs):
        self.merchant_id = kwargs.pop('merchant_id')
        self.password = kwargs.pop('password')
        if kwargs.pop('sandbox', True):
            wsdl_path = 'file://%s/xml/CyberSourceTransaction_1.101.test.wsdl' % (  # noqa
                os.path.dirname(__file__),)
            self.endpoint = (
                'https://ics2wstest.ic3.com/commerce/1.x/transactionProcessor')
        else:
            wsdl_path = 'file://%s/xml/CyberSourceTransaction_1.101.wsdl' % (
                os.path.dirname(__file__),)
            self.endpoint = (
                'https://ics2ws.ic3.com/commerce/1.x/transactionProcessor')
        self.client = suds.client.Client(wsdl_path)
        if 'fingerprint_url' in kwargs:
            self.fingerprint_url = kwargs.pop('fingerprint_url')
        self.org_id = kwargs.pop('org_id', None)
        security_header = suds.wsse.Security()
        security_token = suds.wsse.UsernameToken(
            username=self.merchant_id,
            password=self.password)
        security_header.tokens.append(security_token)
        self.client.set_options(soapheaders=[security_header.xml()])
        super(CyberSourceProvider, self).__init__(*args, **kwargs)

    def get_form(self, data=None):
        if self.payment.status == 'waiting':
            self.payment.change_status('input')
        form = PaymentForm(data, provider=self, payment=self.payment)
        try:
            if form.is_valid():
                raise RedirectNeeded(self.payment.get_success_url())
        except ExternalPostNeeded as e:
            return e.args[0]
        return form

    def _change_status_to_confirmed(self):
        if self.payment.attrs.capture:
            self.payment.captured_amount = self.payment.total
            self.payment.change_status('confirmed')
        else:
            self.payment.change_status('preauth')

    def _set_proper_payment_status_from_reason_code(self, reason_code):
        if reason_code == ACCEPTED:
            self.payment.change_fraud_status('accept', commit=False)
            self._change_status_to_confirmed()
        elif reason_code == FRAUD_MANAGER_REVIEW:
            self.payment.change_fraud_status(
                'review', _(
                    'The order is marked for review by Decision Manager'),
                commit=False)
            self._change_status_to_confirmed()
        elif reason_code == FRAUD_MANAGER_REJECT:
            self.payment.change_fraud_status(
                'reject', _('The order has been rejected by Decision Manager'),
                commit=False)
            self._change_status_to_confirmed()
        elif reason_code == FRAUD_SCORE_EXCEEDS_THRESHOLD:
            self.payment.change_fraud_status(
                'reject', _('Fraud score exceeds threshold.'), commit=False)
            self._change_status_to_confirmed()
        elif reason_code == SMART_AUTHORIZATION_FAIL:
            self.payment.change_fraud_status(
                'reject', _('CyberSource Smart Authorization failed.'),
                commit=False)
            self._change_status_to_confirmed()
        elif reason_code == CARD_VERIFICATION_NUMBER_FAIL:
            self.payment.change_fraud_status(
                'reject', _('Card verification number (CVN) did not match.'),
                commit=False)
            self._change_status_to_confirmed()
        elif reason_code == ADDRESS_VERIFICATION_SERVICE_FAIL:
            self.payment.change_fraud_status(
                'reject', _(
                    'CyberSource Address Verification Service failed.'),
                commit=False)
            self._change_status_to_confirmed()
        else:
            error = self._get_error_message(reason_code)
            self.payment.change_status('error', message=error)
            raise PaymentError(error)

    def charge(self, data):
        if self._capture:
            params = self._prepare_sale(data)
        else:
            params = self._prepare_preauth(data)
        response = self._make_request(params)
        self.payment.attrs.capture = self._capture
        self.payment.transaction_id = response.requestID
        if response.reasonCode == AUTHENTICATE_REQUIRED:
            xid = response.payerAuthEnrollReply.xid
            self.payment.attrs.xid = xid
            self.payment.change_status(
                'waiting',
                message=_('3-D Secure verification in progress'))
            action = response.payerAuthEnrollReply.acsURL
            cc_data = dict(data)
            expiration = cc_data.pop('expiration')
            cc_data['expiration'] = {
                'month': expiration.month,
                'year': expiration.year}
            cc_data = signing.dumps(cc_data)
            payload = {
                'PaReq': response.payerAuthEnrollReply.paReq,
                'TermUrl': self.get_return_url({'token': cc_data}),
                'MD': xid}
            form = BaseForm(data=payload, action=action, autosubmit=True)
            raise ExternalPostNeeded(form)
        else:
            self._set_proper_payment_status_from_reason_code(
                response.reasonCode)

    def capture(self, amount=None):
        if amount is None:
            amount = self.payment.total
        params = self._prepare_capture(amount=amount)
        response = self._make_request(params)
        if response.reasonCode == ACCEPTED:
            self.payment.transaction_id = response.requestID
        elif response.reasonCode == TRANSACTION_SETTLED:
                self.payment.change_status('confirmed')
        else:
            self.payment.save()
            error = self._get_error_message(response.reasonCode)
            raise PaymentError(error)
        return amount

    def release(self):
        params = self._prepare_release()
        response = self._make_request(params)
        if response.reasonCode == ACCEPTED:
            self.payment.transaction_id = response.requestID
        elif response.reasonCode != TRANSACTION_REVERSED:
            self.payment.save()
            error = self._get_error_message(response.reasonCode)
            raise PaymentError(error)

    def refund(self, amount=None):
        if amount is None:
            amount = self.payment.captured_amount
        params = self._prepare_refund(amount=amount)
        response = self._make_request(params)
        self.payment.save()
        if response.reasonCode != ACCEPTED:
            error = self._get_error_message(response.reasonCode)
            raise PaymentError(error)
        return amount

    def _get_error_message(self, code):
        if code in [221, 222, 700, 701, 702, 703]:
            return _(
                'Our bank has flagged your transaction as unusually suspicious. Please contact us to resolve this issue.')  # noqa
        elif code in [201, 203, 209]:
            return _(
                'Your bank has declined the transaction. No additional information was provided.')  # noqa
        elif code == 202:
            return _(
                'The card has either expired or you have entered an incorrect expiration date.')  # noqa
        elif code in [204, 210, 251]:
            return _(
                'There are insufficient funds on your card or it has reached its credit limit.')  # noqa
        elif code == 205:
            return _(
                'The card you are trying to use was reported as lost or stolen.')  # noqa
        elif code == 208:
            return _(
                'Your card is either inactive or it does not permit online payments. Please contact your bank to resolve this issue.')  # noqa
        elif code == 211:
            return _(
                'Your bank has declined the transaction. Please check the verification number of your card and retry.')  # noqa
        elif code == 231:
            return _(
                'Your bank has declined the transaction. Please make sure the card number you have entered is correct and retry.')  # noqa
        elif code in [232, 240]:
            return _(
                'We are sorry but our bank cannot handle the card type you are using.')  # noqa
        elif code in [450, 451, 452, 453, 454, 455,
                      456, 457, 458, 459, 460, 461]:
            return _(
                'We were unable to verify your address. Please make sure the address you entered is correct and retry.')  # noqa
        else:
            return _(
                'We were unable to complete the transaction. Please try again later.')  # noqa

    def _get_params_for_new_payment(self):
        params = {
            'merchantID': self.merchant_id,
            'merchantReferenceCode': self.payment.id,
        }
        try:
            fingerprint_id = self.payment.attrs.fingerprint_session_id
        except KeyError:
            pass
        else:
            params['deviceFingerprintID'] = fingerprint_id
        merchant_defined_data = self._prepare_merchant_defined_data()
        if merchant_defined_data:
            params['merchantDefinedData'] = merchant_defined_data
        return params

    def _make_request(self, params):
        response = self.client.service.runTransaction(**params)
        self.payment.attrs.last_response = self._serialize_response(response)
        return response

    def _prepare_payer_auth_validation_check(self, card_data, pa_response):
        check_service = self.client.factory.create(
            'data:PayerAuthValidateService')
        check_service._run = 'true'
        check_service.signedPARes = pa_response
        params = self._get_params_for_new_payment()
        params['payerAuthValidateService'] = check_service
        if self.payment.attrs.capture:
            service = self.client.factory.create('data:CCCreditService')
            service._run = 'true'
            params['ccCreditService'] = service
        else:
            service = self.client.factory.create('data:CCAuthService')
            service._run = 'true'
            params['ccAuthService'] = service
        params['billTo'] = self._prepare_billing_data()
        params['card'] = self._prepare_card_data(card_data)
        params['item'] = self._prepare_items()
        params['purchaseTotals'] = self._prepare_totals()
        return params

    def _prepare_sale(self, card_data):
        service = self.client.factory.create('data:CCCreditService')
        service._run = 'true'
        check_service = self.client.factory.create(
            'data:PayerAuthEnrollService')
        check_service._run = 'true'
        params = self._get_params_for_new_payment()
        params['ccCreditService'] = service,
        params['payerAuthEnrollService'] = check_service
        params['billTo'] = self._prepare_billing_data()
        params['card'] = self._prepare_card_data(card_data)
        params['item'] = self._prepare_items()
        params['purchaseTotals'] = self._prepare_totals()
        return params

    def _prepare_preauth(self, card_data):
        service = self.client.factory.create('data:CCAuthService')
        service._run = 'true'
        check_service = self.client.factory.create(
            'data:PayerAuthEnrollService')
        check_service._run = 'true'
        params = self._get_params_for_new_payment()
        params['ccAuthService'] = service
        params['payerAuthEnrollService'] = check_service
        params['billTo'] = self._prepare_billing_data()
        params['card'] = self._prepare_card_data(card_data)
        params['item'] = self._prepare_items()
        params['purchaseTotals'] = self._prepare_totals()
        return params

    def _prepare_capture(self, amount=None):
        service = self.client.factory.create('data:CCCaptureService')
        service._run = 'true'
        service.authRequestID = self.payment.transaction_id
        params = {
            'merchantID': self.merchant_id,
            'merchantReferenceCode': self.payment.id,
            'ccCaptureService': service}
        params['purchaseTotals'] = self._prepare_totals(amount=amount)
        return params

    def _prepare_release(self):
        service = self.client.factory.create('data:CCAuthReversalService')
        service._run = 'true'
        service.authRequestID = self.payment.transaction_id
        params = {
            'merchantID': self.merchant_id,
            'merchantReferenceCode': self.payment.id,
            'ccAuthReversalService': service}
        params['purchaseTotals'] = self._prepare_totals()
        return params

    def _prepare_refund(self, amount=None):
        service = self.client.factory.create('data:CCCreditService')
        service._run = 'true'
        service.captureRequestID = self.payment.transaction_id
        params = {
            'merchantID': self.merchant_id,
            'merchantReferenceCode': self.payment.id,
            'ccCreditService': service}
        params['purchaseTotals'] = self._prepare_totals(amount=amount)
        return params

    def _prepare_card_type(self, card_number):
        card_type, card_name = get_credit_card_issuer(card_number)
        if card_type == 'visa':
            return '001'
        elif card_type == 'mastercard':
            return '002'
        elif card_type == 'amex':
            return '003'
        elif card_type == 'jcb':
            return '004'
        elif card_type == 'maestro':
            return '042'

    def _prepare_card_data(self, data):
        card = self.client.factory.create('data:Card')
        card.fullName = data['name']
        card.accountNumber = data['number']
        card.expirationMonth = data['expiration'].month
        card.expirationYear = data['expiration'].year
        card.cvNumber = data['cvv2']
        card.cardType = self._prepare_card_type(data['number'])
        return card

    def _prepare_billing_data(self):
        billing = self.client.factory.create('data:BillTo')
        billing.firstName = self.payment.billing_first_name
        billing.lastName = self.payment.billing_last_name
        billing.street1 = self.payment.billing_address_1
        billing.street2 = self.payment.billing_address_2
        billing.city = self.payment.billing_city
        billing.postalCode = self.payment.billing_postcode
        billing.country = self.payment.billing_country_code
        billing.state = self.payment.billing_country_area
        billing.email = self.payment.billing_email
        billing.ipAddress = self.payment.customer_ip_address
        return billing

    def _prepare_items(self):
        items = []
        for i, item in enumerate(self.payment.get_purchased_items()):
            purchased = self.client.factory.create('data:Item')
            purchased._id = i
            purchased.unitPrice = str(item.price)
            purchased.quantity = str(item.quantity)
            purchased.productName = item.name
            purchased.productSKU = item.sku
            items.append(purchased)
        return items

    def _prepare_merchant_defined_data(self):
        try:
            merchant_defined_data = self.payment.attrs.merchant_defined_data
        except KeyError:
            return
        else:
            data = self.client.factory.create('data:MerchantDefinedData')
            for i, value in merchant_defined_data.iteritems():
                field = self.client.factory.create('data:MDDField')
                field._id = int(i)
                field.value = str(value)
                data.mddField.append(field)
            return data

    def _prepare_totals(self, amount=None):
        totals = self.client.factory.create('data:PurchaseTotals')
        totals.currency = self.payment.currency
        if amount is None:
            totals.grandTotalAmount = str(self.payment.total)
            totals.freightAmount = str(self.payment.delivery)
        else:
            totals.grandTotalAmount = str(amount)
        return totals

    def _serialize_response(self, response):
        if isinstance(response, (Element, Object)):
            response = dict(response)
            for k, v in response.items():
                response[k] = self._serialize_response(v)
        return response

    def process_data(self, request):
        xid = request.POST.get('MD')
        if xid != self.payment.attrs.xid:
            return redirect(self.payment.get_failure_url())
        if self.payment.status in ['confirmed', 'preauth']:
            return redirect(self.payment.get_success_url())
        cc_data = request.GET.get('token')
        try:
            cc_data = signing.loads(cc_data)
        except:
            return redirect(self.payment.get_failure_url())
        else:
            expiration = cc_data['expiration']
            cc_data['expiration'] = datetime.date(
                expiration['year'], expiration['month'], 1)
        params = self._prepare_payer_auth_validation_check(
            cc_data, request.POST.get('PaRes'))
        response = self._make_request(params)
        self.payment.transaction_id = response.requestID
        self._set_proper_payment_status_from_reason_code(
            response.reasonCode)
        if self.payment.status in ['confirmed', 'preauth']:
            return redirect(self.payment.get_success_url())
        else:
            return redirect(self.payment.get_failure_url())
