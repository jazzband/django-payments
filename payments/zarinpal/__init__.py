from payments.core import BasicProvider
from payments import PaymentStatus, RedirectNeeded
from payments.forms import PaymentForm

from django.shortcuts import redirect
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse


from collections import OrderedDict


from zeep.client import Client


class ZarinpalProvider(BasicProvider):
    _web_service = "https://www.zarinpal.com/pg/services/WebGate/wsdl"

    def __init__(self, merchant_code, web_service=_web_service, **kwargs):
        self._merchant_code = merchant_code
        self._web_service = web_service
        self._capture = True
        self.USE_SSL = True

        if not self._capture:
            raise ImproperlyConfigured(
                'Zarinpal service does not support pre-authorization.')


    def get_form(self, payment, data=None):
        client = Client(self._web_service)
        # converting rial to tooman
        amount = int(payment.total // 10)
        
        description = payment.description
        CallbackURL = payment.get_return_url()
        result = client.service.PaymentRequest(MerchantID=self._merchant_code,
                                               Amount=amount,
                                               #    email,
                                               #    mobile,
                                               Description=description,
                                               CallbackURL=CallbackURL)


        redirect_url = 'https://www.zarinpal.com/pg/StartPay/' + str(result.Authority)


        if result.Status == 100:
            payment.change_status(PaymentStatus.INPUT)
            raise RedirectNeeded(redirect_url)


    def process_data(self, payment, request, **kwargs):
        # Verifying the payment
        amount = int(payment.total // 10)
        pay = payment.change_status(PaymentStatus.CONFIRMED)
        client = Client(self._web_service)
        if request.GET.get('Status') == 'OK':
            result = client.service.PaymentVerification(self._merchant_code,
                                                        request.GET['Authority'],
                                                        amount)
            if result.Status == 100:
                payment.change_status(PaymentStatus.CONFIRMED)
                # return HttpResponse('Transaction success. RefID: ' + str(result.RefID))
            elif result.Status == 101:
                payment.change_status(PaymentStatus.WAITING)
                # return HttpResponse('Transaction submitted : ' + str(result.Status))
                
            else:
                payment.change_status(PaymentStatus.REJECTED)
                # return HttpResponse('Transaction failed. Status: ' + str(result.Status))
        else:
            # return HttpResponse('Transaction failed or canceled by user')
            payment_track_id = result.RefID

        payment.save()
        return 


    def capture(self, payment, amount=None):
        payment.change_status(PaymentStatus.CONFIRMED)
        return amount

    def release(self, payment):
        return None

    def refund(self, payment, amount=None):
        return 0
