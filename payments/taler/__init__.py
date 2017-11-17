#  This file is part of DJANGO-PAYMENTS
#  (C) 2017 Taler Systems SA
#
#  This library is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2.1 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
#  @author Marcello Stanisci

from django.utils.translation import ugettext as _
from django.template.loader import render_to_string
import json
from django.shortcuts import redirect
from ..core import BasicProvider, get_base_url
from .. import RedirectNeeded, PaymentStatus
import re
from django.http import HttpResponse, JsonResponse
import requests
from urllib.parse import urljoin
import logging
from django.conf import settings
from .amount import Amount, BadAmount

logger = logging.getLogger(__name__)

class TalerProvider(BasicProvider):
    '''
    GNU Taler payment provider
    '''

    def __init__(self, backend_url, address, name, jurisdiction, instance=None):

        # The backend URL is served by the C backend, it is
        # used to sign data coming from the frontend and to
        # communicate with the exchange.
        # Its URL must end with a slash, like 'http://backend.demo.taler.net/'.
        self.backend_url = backend_url
        # Token which identifies this frontend to the backend.  In fact,
        # any backend can support multiple frontends, and 'None' is the
        # default one.
        self.instance = instance
        # Physical address and jurisdiction, and shop name
        self.address = address
        self.name = name
        self.jurisdiction = jurisdiction
        super(TalerProvider, self)

    # This function gets called when the user chooses the
    # payment method to use.  It will redirect the user to
    # the page returning 402+contract_url.
    def get_form(self, payment, data=None):
        raise RedirectNeeded(self.get_return_url(payment))

    # Design note: in django-payments, there is usually ONE URL that
    # processes the payment, thus decisions are taken on the basis of
    # the _state_ of the payment, rather than a particular endpoint.
    # For example, it is perfectly normal having fulfillment and pay
    # URL being the same thing.

    def process_data(self, payment, request):

        # Very first branch taken.  It returns the 402 status
        # plus the contract generation URL.
        if payment.status == PaymentStatus.WAITING:
            wallet_not_found_msg = _('Taler wallet disabled.  Please' \
                ' either enable the wallet or pick another payment method.')
            data = render_to_string('payments/taler_fallback.html',
                                   {'msg': wallet_not_found_msg})
            response = HttpResponse(data, status=402)

            response['X-Taler-Contract-Url'] = self.get_return_url(payment)
            payment.change_status(PaymentStatus.INPUT)
            return response

        # Listen for contract generation.
        if payment.status == PaymentStatus.INPUT:
            try:
                total_amount = Amount.parse('%s:%0.2f' % (payment.currency, payment.total)).dump()
                order = {
                    'summary': payment.message,
                    'nonce': request.GET.get('nonce'),
                    'amount': total_amount,
                    'products': [{'description': payment.description,
                                  'quantity': 1,
                                  'product_id': 0,
                                  'price': total_amount}],
                    'fulfillment_url': self.get_return_url(payment),
                    'pay_url': self.get_return_url(payment),
                    'merchant': {
                        'instance': self.instance,
                        'address': self.address,
                        'name': self.name,
                        'jurisdiction': self.jurisdiction},
                    'extra': {}}
            except BadAmount as e:
                logger.error('Malformed amount: %s' % e.faulty_str)
                data = {'error': _('Internal error generating contract'),
                                   'detail': _('Could not parse amount')}
                return JsonResponse(data, status=500)

            try:
                r = requests.post(urljoin(self.backend_url, 'proposal'),
                                  json={'order': order})
            except requests.RequestException as e:
                logger.error(e)
                return JsonResponse({'error': 'Internal server error',
                    'detail': 'Could not reach the backend'}, status=500)
            if r.status_code == 200:
                payment.change_status(PaymentStatus.PREAUTH)
            return JsonResponse(r.json(), status=r.status_code)

        # This is responsible to both execute the payment and receive it.
        # When the wallet attempts to GET it, it returns the 402 which
        # executes the payment, whereas POSTing to it triggers the /pay behaviour.
        if payment.status == PaymentStatus.PREAUTH:
            if request.method == 'POST':
                try:
                    r = requests.post(urljoin(self.backend_url, 'pay'),
                                      json=json.loads(request.body.decode('utf-8')))
                except requests.RequestException as e:
                    logger.error(e)
                    return JsonResponse({'error': 'Internal server error',
                        'detail': 'Could not reach the backend'}, status=500)
                if r.status_code == 200:
                    payment.change_status(PaymentStatus.CONFIRMED)
                return JsonResponse(r.json(), status=r.status_code)

            if request.method == 'GET':
                wallet_not_found_msg = _('Taler wallet disabled.  Please' \
                    ' either enable the wallet or pick another payment method.')
                data = render_to_string('payments/taler_fallback.html',
                                       {'msg': wallet_not_found_msg})
                response = HttpResponse(data, status=402)
                response['X-Taler-Contract-Url'] = self.get_return_url(payment)
                response['X-Taler-Offer-Url'] = get_base_url()
                return response

        # Taken when the payment has gone through, redirect to persistent
        # fulfillment page.
        if payment.status == PaymentStatus.CONFIRMED:
            # returns absolute url
            return redirect(payment.get_success_url())

        # This should _never_ happen
        return JsonResponse({'error': 'Internal server error',
            'detail': 'Unknown payment status!'}, status=500)
