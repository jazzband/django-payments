import json
import logging
import re

from django.http import HttpResponse
from django.shortcuts import redirect
from mercadopago import MP

from payments import PaymentError
from payments import PaymentStatus
from payments import RedirectNeeded
from payments.core import BasicProvider

logger = logging.getLogger(__name__)

STATUS_MAP = {
    "pending": PaymentStatus.WAITING,
    "approved": PaymentStatus.CONFIRMED,
    "authorized": PaymentStatus.PREAUTH,
    "in_process": PaymentStatus.WAITING,
    "in_mediation": PaymentStatus.WAITING,
    "rejected": PaymentStatus.REJECTED,
    "cancelled": PaymentStatus.ERROR,
    "refunded": PaymentStatus.REFUNDED,
    "charged_back": PaymentStatus.REFUNDED,
}


class MercadoPagoProvider(BasicProvider):
    def __init__(self, client_id, secret_key, sandbox):
        # self._capture = True
        self.client = MP(client_id, secret_key)
        self.client.sandbox_mode(sandbox)
        self.is_sandbox = sandbox

    def get_or_create_preference(self, payment):
        if payment.transaction_id:
            return self.get_preference(payment)
        else:
            return self.create_preference(payment)

    def get_preference(self, payment):
        if not payment.transaction_id:
            raise ValueError("This payment does not have a preference.")

        result = self.client.get_preference(payment.transaction_id)

        if result["status"] >= 300:
            raise Exception("Failed to retrieve MercadoPago preference.", result)

        return result["response"]

    def create_preference(self, payment):
        if payment.transaction_id:
            raise ValueError("This payment already has a preference.")

        payload = {
            "auto_return": "all",
            "items": [
                {
                    # "category_id": "services",
                    "currency_id": item.currency,
                    "description": item.sku,
                    "quantity": item.quantity,
                    "title": item.name,
                    "unit_price": float(item.price),
                }
                for item in payment.get_purchased_items()
            ],
            "external_reference": payment.transaction_id,
            "back_urls": {
                "success": self.get_return_url(payment),
                "pending": self.get_return_url(payment),
                "failure": self.get_return_url(payment),
            },
            "notification_url": self.get_return_url(payment),
            "statement_descriptor": payment.description,
        }
        # Payment objects can implement "get_shipment" to use MercadoPago's
        # shipping service.
        if hasattr(payment, "get_shipment"):
            shipments = payment.get_shipment()
            if shipments:
                payload["shipments"] = shipments

        logger.debug("Creating preference with payload: %s", payload)
        result = self.client.create_preference(payload)

        if result["status"] >= 300:
            raise Exception("Failed to create MercadoPago preference.", result)

        payment.transaction_id = result["response"]["id"]
        payment.save()

        return result["response"]

    def get_action(self, payment):
        # This is the form-action. But we don't use a form.
        raise NotImplementedError()

    def process_notification(self, payment, request):
        data = json.loads(request.body)

        logger.debug(
            "Got notification from mercadopago for %s, params: %s, body: %s.",
            payment.pk,
            request.GET,
            data,
        )

        topic = data.get("topic", None)
        resource = data.get("resource", None)

        if topic == "payment":
            match = re.search(r"(\d+)", resource)
            collection_id = match.groups()[0]
            self.process_collection(payment, collection_id)

        return HttpResponse("Thanks")

    def process_callback(self, payment, request):
        collection_id = request.GET.get("collection_id", None)
        if not collection_id.isdigit():
            return redirect(payment.get_failure_url())

        self.process_collection(payment, collection_id)

        return redirect(payment.get_success_url())

    def process_collection(self, payment, collection_id):
        response = self.client.get_payment_info(collection_id)
        if response["status"] != 200:
            message = "MercadoPago sent invalid payment data."
            payment.change_status(PaymentStatus.ERROR, message)
            raise PaymentError(message)

        upstream_status = response["response"]["status"]
        payment.change_status(STATUS_MAP[upstream_status])

    def process_data(self, payment, request):
        if request.method == "GET":
            return self.process_callback(payment, request)
        elif request.method == "POST":
            return self.process_notification(payment, request)

    def get_form(self, payment, data=None):
        # There's not for for MP, we need to redirect to their checkout page.
        preference = self.get_or_create_preference(payment)
        logger.debug("Got preference: %s", preference)

        if self.is_sandbox:
            url = preference["sandbox_init_point"]
        else:
            url = preference["init_point"]

        raise RedirectNeeded(url)

    def refund(self, payment, amount=None):
        raise NotImplementedError()
