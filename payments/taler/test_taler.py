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

from __future__ import unicode_literals
import json
from unittest import TestCase
from . import TalerProvider
from mock import patch, MagicMock, Mock
from .. import RedirectNeeded, PaymentStatus
from decimal import Decimal

class Payment(Mock):
    status = PaymentStatus.WAITING
    message = 'mocked payment'
    total = Decimal(10)
    description = 'mocked payment object'
    instance = 'mock instance'
    address = 'mock address'
    name = 'mock name'
    jurisdiction = 'mock jurisdiction'
    currency = 'MOCK'

    def get_process_url(self):
        return 'mock-process-url'

    def get_success_url(self):
        return 'http://example.com/mock-success'

    def change_status(self, status):
        self.status = status

class TestTalerProvider(TestCase):

    def setUp(self):
        self.payment = Payment()
        self.provider = TalerProvider(backend_url='http://mocked_backend_url',
            instance='mock_instance', address='mock address',
            name='mock name', jurisdiction='mock jurisdiction')

    # This tests the very first redirect, then one that
    # redirects to the first 402 page.
    def test_provider_redirects_to_contract_url(self):
        with self.assertRaises(RedirectNeeded):
            self.provider.get_form(self.payment)

    # Test whether a contract generation url is returned
    # along with the 402 status code.
    def test_provider_contract_generation_header(self):
        response = self.provider.process_data(self.payment, MagicMock())
        self.assertTrue(response.get('X-Taler-Contract-Url'))
        self.assertFalse(response.get('X-Taler-Offer-Url'))
        self.assertEqual(response.status_code, 402)
        self.assertEqual(self.payment.status, PaymentStatus.INPUT)

    # Test whether the frontend logic interacts well with backend.
    @patch('requests.post')
    def test_provider_contract_generation(self, mocked_post):
        request = MagicMock()
        request.GET = {'nonce': 'nonce098'}
        data = MagicMock()
        data.return_value = {'not': 'changed'}
        post = MagicMock()
        post.status_code = 200
        post.json = data
        mocked_post.return_value = post
        self.payment.change_status(PaymentStatus.INPUT)
        r = self.provider.process_data(self.payment, request)
        total_amount = {
            'value': 10,
            'fraction': 0,
            'currency': self.payment.currency}
        expected_order = {'order': {
            'summary': self.payment.message,
            'nonce': 'nonce098',
            'amount': total_amount,
            'products': [{
                'description': self.payment.description,
                'quantity': 1,
                'product_id': 0,
                'price': total_amount}],
            'fulfillment_url': 'https://example.com/mock-process-url',
            'pay_url': 'https://example.com/mock-process-url',
            'merchant': {
                'instance': self.provider.instance,
                'address': self.provider.address,
                'name': self.provider.name,
                'jurisdiction': self.provider.jurisdiction},
                'extra': {}}}
        mocked_post.assert_called_with('http://mocked_backend_url/proposal',
                                       json=expected_order)
        self.assertEqual(self.payment.status, PaymentStatus.PREAUTH)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(json.dumps(data.return_value), r.content.decode('utf-8'))

    # Testing second returned 402, the one returned by GETting the
    # process url having the PREAUTH status.  This logic is triggered
    # rigth after the user confirms the payment.
    def test_provider_trigger_payment(self):
        request = MagicMock()
        request.method = 'GET'
        self.payment.change_status(PaymentStatus.PREAUTH)
        r = self.provider.process_data(self.payment, request)
        self.assertEqual(r.status_code, 402)
        self.assertTrue(r.get('X-Taler-Contract-Url'))
        self.assertTrue(r.get('X-Taler-Offer-Url'))

    # Testing coins receiving logic.
    @patch('requests.post')
    def test_provider_receive_payment(self, mocked_post):
        data = MagicMock()
        data.return_value = {'not': 'changed'}
        post = MagicMock()
        post.status_code = 200
        post.json = data
        mocked_post.return_value = post
        self.payment.change_status(PaymentStatus.PREAUTH)
        request = MagicMock()
        request.method = 'POST'
        request.body = b'{"mock": "coins"}'
        r = self.provider.process_data(self.payment, request)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.payment.status, PaymentStatus.CONFIRMED)
        mocked_post.assert_called_with('http://mocked_backend_url/pay',
            json={'mock': 'coins'})
        self.assertEqual(json.dumps(data.return_value), r.content.decode('utf-8'))

    # Test whether successful payment gets redirected to
    # "success url"
    @patch('payments.taler.redirect')
    def test_provider_success_payment(self, mocked_redirect):
        self.payment.change_status(PaymentStatus.CONFIRMED)
        self.provider.process_data(self.payment, MagicMock())
        mocked_redirect.assert_called_with('http://example.com/mock-success')

    # Test unknown payment status, should never happen
    def test_provider_unknown_payment_status(self):
        self.payment.change_status("does not exist")
        r = self.provider.process_data(self.payment, MagicMock())
        self.assertEqual(r.status_code, 500)
