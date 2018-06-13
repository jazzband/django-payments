from payments.core import BasicProvider
from payments import PaymentStatus
from payments.forms import PaymentForm

from django.shortcuts import redirect
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse

from zeep.client import Client


class ZarinpalProvider(BasicProvider):
    _web_service = "https://www.zarinpal.com/pg/services/WebGate/wsdl"

    def __init__(self, merchant_code, web_service=_web_service, **kwargs):
        self._merchant_code = merchant_code
        self._web_service = web_service
        self._capture = True
        self.USE_SSL = False

        if not self._capture:
            raise ImproperlyConfigured(
                'Sagepay does not support pre-authorization.')

    def get_form(self, payment, data=None):
        # print("::::::::::::::enter form:::::::::::::")
        client = Client(self._web_service)
        # converting rial to tooman
        amount = payment.total / 10
        description = "صفحه ی خرید"
        CallbackURL = "https://arput.com"
        result = client.service.PaymentRequest(MerchantID=self._merchant_code,
                                               Amount=amount,
                                               #    email,
                                               #    mobile,
                                               Description=description,
                                               CallbackURL=CallbackURL)
        # print("::::::::::::::get pay url:::::::::::::")
        if result.Status == 100:
            payment.changestatus(PaymentStatus.INPUT)
            # print("::::::::::::REDIRECT::::::::::::::;")
            # return redirect('https://www.zarinpal.com/pg/StartPay/' + result.Authority)
        # else:
        #     return {}
        #     return HttpResponse('Error')

        form = PaymentForm(data=data, payment=payment, provider=self)

        if form.is_valid():
            raise RedirectNeeded(payment.get_success_url())
        return form

    # def get_hidden_fields(self, payment):
    #     print("::::::::::::::enter payment:::::::::::::")
    #     client = Client(self._web_service)
    #     print("::::::::::::::enter payment:::::::::::::")
    #     # converting rial to tooman
    #     amount = payment.total / 10
    #     description = "صفحه ی خرید"
    #     CallbackURL = "https://arput.com"
    #     result = client.service.PaymentRequest(self._merchant_code,
    #                                            amount,
    #                                            description,
    #                                            #    email,
    #                                            #    mobile,
    #                                            CallbackURL)
    #     if result.Status == 100:
    #         payment.changestatus(PaymentStatus.WAITING)
    #         print("::::::::::::REDIRECT::::::::::::::;")
    #         return redirect('https://www.zarinpal.com/pg/StartPay/' + result.Authority)
    #     else:
    #         return {}
    #         # return HttpResponse('Error')

    def get_action(self, payment, request):
        # print(":::::::::::::verify payment:::::::::")
        # amount = payment.total
        # pay = payment.changestatus(PaymentStatus.CONFIRMED)
        # client = Client(self._web_service)
        # if request.GET.get('Status') == 'OK':
        #     result = client.service.PaymentVerification(self._merchant_code,
        #                                                 request.GET['Authority'],
        #                                                 amount)
        #     if result.Status == 100:
        #         pay = payment.changestatus(PaymentStatus.CONFIRMED)
        #         # return HttpResponse('Transaction success. RefID: ' + str(result.RefID))
        #     elif result.Status == 101:
        #         payment = payment.changestatus(PaymentStatus.CONFIRMED)
        #         # return HttpResponse('Transaction submitted : ' + str(result.Status))
        #     else:
        #         payment = payment.changestatus(PaymentStatus.REJECTED)
        #         # return HttpResponse('Transaction failed. Status: ' + str(result.Status))
        # else:
        #     # return HttpResponse('Transaction failed or canceled by user')
        #     payment_track_id = result.RefID
        return

    def capture(self, payment, amount=None):
        payment.changestatus(PaymentStatus.CONFIRMED)
        return amount

    def release(self, payment):
        return None

    def refund(self, payment, amount=None):
        return 0
