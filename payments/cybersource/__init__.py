import datetime
import os.path

import suds.client
import suds.wsse
from django.core import signing
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from suds.sax.element import Element
from suds.sudsobject import Object

from .. import ExternalPostNeeded
from .. import FraudStatus
from .. import PaymentError
from .. import PaymentStatus
from .. import RedirectNeeded
from ..core import BasicProvider
from ..core import get_credit_card_issuer
from ..forms import PaymentForm as BaseForm
from .forms import PaymentForm


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

WSDL_PATH_TEST = 'xml/CyberSourceTransaction_1.101.test.wsdl'
WSDL_PATH = 'xml/CyberSourceTransaction_1.101.wsdl'


class CyberSourceProvider(BasicProvider):
    """Payment provider for CyberSource

    This backend implements payments using `Cybersource
    <http://www.cybersource.com/www/>`_.

    This backend supports fraud detection.

    :param merchant_id: Your Merchant ID
    :param password: Generated transaction security key for the SOAP toolkit
    :param org_id: Provide this parameter to enable Cybersource Device Fingerprinting
    :param fingerprint_url: Address of the fingerprint server
    :param sandbox: Whether to use a sandbox environment for testing
    :param capture: Whether to capture the payment automatically.  See
        :ref:`capture-payments` for more details.
    """

    fingerprint_url: str

    def __init__(
        self, merchant_id, password, org_id=None,
        fingerprint_url='https://h.online-metrix.net/fp/', sandbox=True,
        capture=True,
    ):
        self.merchant_id = merchant_id
        self.password = password
        local_path = os.path.dirname(__file__)
        if os.path.sep != '/':
            # ugly hack for urllib and Windows
            local_path = local_path.replace(os.path.sep, '/')
        if not local_path.startswith('/'):
            # windows paths don't start with '/'
            local_path = f'/{local_path}'
        if sandbox:
            wsdl_path = f'file://{local_path}/{WSDL_PATH_TEST}'
            self.endpoint = (
                'https://ics2wstest.ic3.com/commerce/1.x/transactionProcessor')
        else:
            wsdl_path = f'file://{local_path}/{WSDL_PATH}'
            self.endpoint = (
                'https://ics2ws.ic3.com/commerce/1.x/transactionProcessor')
        self.client = suds.client.Client(wsdl_path)
        self.fingerprint_url = fingerprint_url
        self.org_id = org_id
        security_header = suds.wsse.Security()
        security_token = suds.wsse.UsernameToken(
            username=self.merchant_id,
            password=self.password)
        security_header.tokens.append(security_token)
        self.client.set_options(soapheaders=[security_header.xml()])
        super().__init__(capture=capture)

    def get_form(self, payment, data=None):
        if payment.status == PaymentStatus.WAITING:
            payment.change_status(PaymentStatus.INPUT)
        form = PaymentForm(data, provider=self, payment=payment)
        try:
            if form.is_valid():
                raise RedirectNeeded(payment.get_success_url())
        except ExternalPostNeeded as e:
            return e.args[0]
        return form

    def _change_status_to_confirmed(self, payment):
        if self._capture:
            payment.captured_amount = payment.total
            payment.change_status(PaymentStatus.CONFIRMED)
        else:
            payment.change_status(PaymentStatus.PREAUTH)

    def _set_proper_payment_status_from_reason_code(self, payment, reason_code):
        if reason_code == ACCEPTED:
            payment.change_fraud_status(FraudStatus.ACCEPT, commit=False)
            self._change_status_to_confirmed(payment)
        elif reason_code == FRAUD_MANAGER_REVIEW:
            payment.change_fraud_status(
                FraudStatus.REVIEW,
                _('The order is marked for review by Decision Manager'),
                commit=False)
            self._change_status_to_confirmed(payment)
        elif reason_code == FRAUD_MANAGER_REJECT:
            payment.change_fraud_status(
                FraudStatus.REJECT, _('The order has been rejected by Decision Manager'),
                commit=False)
            self._change_status_to_confirmed(payment)
        elif reason_code == FRAUD_SCORE_EXCEEDS_THRESHOLD:
            payment.change_fraud_status(
                FraudStatus.REJECT, _('Fraud score exceeds threshold.'), commit=False)
            self._change_status_to_confirmed(payment)
        elif reason_code == SMART_AUTHORIZATION_FAIL:
            payment.change_fraud_status(
                FraudStatus.REJECT, _('CyberSource Smart Authorization failed.'),
                commit=False)
            self._change_status_to_confirmed(payment)
        elif reason_code == CARD_VERIFICATION_NUMBER_FAIL:
            payment.change_fraud_status(
                FraudStatus.REJECT, _('Card verification number (CVN) did not match.'),
                commit=False)
            self._change_status_to_confirmed(payment)
        elif reason_code == ADDRESS_VERIFICATION_SERVICE_FAIL:
            payment.change_fraud_status(
                FraudStatus.REJECT, _(
                    'CyberSource Address Verification Service failed.'),
                commit=False)
            self._change_status_to_confirmed(payment)
        else:
            error = self._get_error_message(reason_code)
            payment.change_status(PaymentStatus.ERROR, message=error)
            raise PaymentError(error)

    def charge(self, payment, data):
        if self._capture:
            params = self._prepare_sale(payment, data)
        else:
            params = self._prepare_preauth(payment, data)
        response = self._make_request(payment, params)
        payment.attrs.capture = self._capture
        payment.transaction_id = response.requestID
        if response.reasonCode == AUTHENTICATE_REQUIRED:
            xid = response.payerAuthEnrollReply.xid
            payment.attrs.xid = xid
            payment.change_status(
                PaymentStatus.WAITING,
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
                'TermUrl': self.get_return_url(payment, {'token': cc_data}),
                'MD': xid}
            form = BaseForm(data=payload, action=action, autosubmit=True)
            raise ExternalPostNeeded(form)
        else:
            self._set_proper_payment_status_from_reason_code(
                payment, response.reasonCode)

    def capture(self, payment, amount=None):
        if amount is None:
            amount = payment.total
        params = self._prepare_capture(payment, amount=amount)
        response = self._make_request(payment, params)
        if response.reasonCode == ACCEPTED:
            payment.transaction_id = response.requestID
        elif response.reasonCode == TRANSACTION_SETTLED:
            payment.change_status(PaymentStatus.CONFIRMED)
        else:
            payment.save()
            error = self._get_error_message(response.reasonCode)
            raise PaymentError(error)
        return amount

    def release(self, payment):
        params = self._prepare_release(payment)
        response = self._make_request(payment, params)
        if response.reasonCode == ACCEPTED:
            payment.transaction_id = response.requestID
        elif response.reasonCode != TRANSACTION_REVERSED:
            payment.save()
            error = self._get_error_message(response.reasonCode)
            raise PaymentError(error)

    def refund(self, payment, amount=None):
        if amount is None:
            amount = payment.captured_amount
        params = self._prepare_refund(payment, amount=amount)
        response = self._make_request(payment, params)
        payment.save()
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

    def _get_params_for_new_payment(self, payment):
        params = {
            'merchantID': self.merchant_id,
            'merchantReferenceCode': payment.id,
        }
        try:
            fingerprint_id = payment.attrs.fingerprint_session_id
        except KeyError:
            pass
        else:
            params['deviceFingerprintID'] = fingerprint_id
        merchant_defined_data = self._prepare_merchant_defined_data(payment)
        if merchant_defined_data:
            params['merchantDefinedData'] = merchant_defined_data
        return params

    def _make_request(self, payment, params):
        response = self.client.service.runTransaction(**params)
        payment.attrs.last_response = self._serialize_response(response)
        return response

    def _prepare_payer_auth_validation_check(self, payment, card_data,
                                             pa_response):
        check_service = self.client.factory.create(
            'data:PayerAuthValidateService')
        check_service._run = 'true'
        check_service.signedPARes = pa_response
        params = self._get_params_for_new_payment(payment)
        params['payerAuthValidateService'] = check_service
        if payment.attrs.capture:
            service = self.client.factory.create('data:CCCreditService')
            service._run = 'true'
            params['ccCreditService'] = service
        else:
            service = self.client.factory.create('data:CCAuthService')
            service._run = 'true'
            params['ccAuthService'] = service
        params.update({
            'billTo': self._prepare_billing_data(payment),
            'card': self._prepare_card_data(card_data),
            'item': self._prepare_items(payment),
            'purchaseTotals': self._prepare_totals(payment)})
        return params

    def _prepare_sale(self, payment, card_data):
        service = self.client.factory.create('data:CCCreditService')
        service._run = 'true'
        check_service = self.client.factory.create(
            'data:PayerAuthEnrollService')
        check_service._run = 'true'
        params = self._get_params_for_new_payment(payment)
        params.update({
            'ccCreditService': service,
            'payerAuthEnrollService': check_service,
            'billTo': self._prepare_billing_data(payment),
            'card': self._prepare_card_data(card_data),
            'item': self._prepare_items(payment),
            'purchaseTotals': self._prepare_totals(payment)})
        return params

    def _prepare_preauth(self, payment, card_data):
        service = self.client.factory.create('data:CCAuthService')
        service._run = 'true'
        check_service = self.client.factory.create(
            'data:PayerAuthEnrollService')
        check_service._run = 'true'
        params = self._get_params_for_new_payment(payment)
        params.update({
            'ccAuthService': service,
            'payerAuthEnrollService': check_service,
            'billTo': self._prepare_billing_data(payment),
            'card': self._prepare_card_data(card_data),
            'item': self._prepare_items(payment),
            'purchaseTotals': self._prepare_totals(payment)})
        return params

    def _prepare_capture(self, payment, amount=None):
        service = self.client.factory.create('data:CCCaptureService')
        service._run = 'true'
        service.authRequestID = payment.transaction_id
        params = {
            'merchantID': self.merchant_id,
            'merchantReferenceCode': payment.id,
            'ccCaptureService': service,
            'purchaseTotals': self._prepare_totals(payment, amount=amount)}
        return params

    def _prepare_release(self, payment):
        service = self.client.factory.create('data:CCAuthReversalService')
        service._run = 'true'
        service.authRequestID = payment.transaction_id
        params = {
            'merchantID': self.merchant_id,
            'merchantReferenceCode': payment.id,
            'ccAuthReversalService': service,
            'purchaseTotals': self._prepare_totals(payment)}
        return params

    def _prepare_refund(self, payment, amount=None):
        service = self.client.factory.create('data:CCCreditService')
        service._run = 'true'
        service.captureRequestID = payment.transaction_id
        params = {
            'merchantID': self.merchant_id,
            'merchantReferenceCode': payment.id,
            'ccCreditService': service,
            'purchaseTotals': self._prepare_totals(payment, amount=amount)}
        return params

    def _prepare_card_type(self, card_number):
        card_type, card_name = get_credit_card_issuer(card_number)
        if card_type == 'visa':
            return '001'
        elif card_type == 'mastercard':
            return '002'
        elif card_type == 'amex':
            return '003'
        elif card_type == 'discover':
            return '004'
        elif card_type == 'diners':
            return'005'
        elif card_type == 'jcb':
            return '007'
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

    def _prepare_billing_data(self, payment):
        billing = self.client.factory.create('data:BillTo')
        billing.firstName = payment.billing_first_name
        billing.lastName = payment.billing_last_name
        billing.street1 = payment.billing_address_1
        billing.street2 = payment.billing_address_2
        billing.city = payment.billing_city
        billing.postalCode = payment.billing_postcode
        billing.country = payment.billing_country_code
        billing.state = payment.billing_country_area
        billing.email = payment.billing_email
        billing.ipAddress = payment.customer_ip_address
        return billing

    def _prepare_items(self, payment):
        items = []
        for i, item in enumerate(payment.get_purchased_items()):
            purchased = self.client.factory.create('data:Item')
            purchased._id = i
            purchased.unitPrice = str(item.price)
            purchased.quantity = str(item.quantity)
            purchased.productName = item.name
            purchased.productSKU = item.sku
            items.append(purchased)
        return items

    def _prepare_merchant_defined_data(self, payment):
        try:
            merchant_defined_data = payment.attrs.merchant_defined_data
        except KeyError:
            return
        else:
            data = self.client.factory.create('data:MerchantDefinedData')
            for i, value in merchant_defined_data.items():
                field = self.client.factory.create('data:MDDField')
                field._id = int(i)
                field.value = value
                data.mddField.append(field)
            return data

    def _prepare_totals(self, payment, amount=None):
        totals = self.client.factory.create('data:PurchaseTotals')
        totals.currency = payment.currency
        if amount is None:
            totals.grandTotalAmount = str(payment.total)
            totals.freightAmount = str(payment.delivery)
        else:
            totals.grandTotalAmount = str(amount)
        return totals

    def _serialize_response(self, response):
        if isinstance(response, (Element, Object)):
            response = dict(response)
            for k, v in response.items():
                response[k] = self._serialize_response(v)
        return response

    def process_data(self, payment, request):
        xid = request.POST.get('MD')
        if xid != payment.attrs.xid:
            return redirect(payment.get_failure_url())
        if payment.status in [PaymentStatus.CONFIRMED, PaymentStatus.PREAUTH]:
            return redirect(payment.get_success_url())
        cc_data = request.GET.get('token')
        try:
            cc_data = signing.loads(cc_data)
        except Exception:
            return redirect(payment.get_failure_url())
        else:
            expiration = cc_data['expiration']
            cc_data['expiration'] = datetime.date(
                expiration['year'], expiration['month'], 1)
        params = self._prepare_payer_auth_validation_check(
            payment, cc_data, request.POST.get('PaRes'))
        response = self._make_request(payment, params)
        payment.transaction_id = response.requestID
        try:
            self._set_proper_payment_status_from_reason_code(
                payment, response.reasonCode)
        except PaymentError:
            pass
        if payment.status in [PaymentStatus.CONFIRMED, PaymentStatus.PREAUTH]:
            return redirect(payment.get_success_url())
        else:
            return redirect(payment.get_failure_url())
