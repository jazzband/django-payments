import hashlib

from django import forms

from .. import PaymentStatus

NEW = "new"
PROCESSING = "processing"
COMPLETED = "completed"
REJECTED = "rejected"
PROCESSING_REALIZATION_WAITING = "processing_realization_waiting"
PROCESSING_REALIZATION = "processing_realization"


class ProcessPaymentForm(forms.Form):

    id = forms.CharField(required=False)
    operation_number = forms.CharField(required=False)
    operation_type = forms.CharField(required=False)
    operation_status = forms.CharField(required=False)
    operation_amount = forms.CharField(required=False)
    operation_currency = forms.CharField(required=False)
    operation_withdrawal_amount = forms.CharField(required=False)
    operation_commission_amount = forms.CharField(required=False)
    is_completed = forms.CharField(required=False)
    operation_original_amount = forms.CharField(required=False)
    operation_original_currency = forms.CharField(required=False)
    operation_datetime = forms.CharField(required=False)
    operation_related_number = forms.CharField(required=False)
    control = forms.CharField(required=False)
    description = forms.CharField(required=False)
    email = forms.CharField(required=False)
    p_info = forms.CharField(required=False)
    p_email = forms.CharField(required=False)
    credit_card_issuer_identification_number = forms.CharField(required=False)
    credit_card_masked_number = forms.CharField(required=False)
    credit_card_brand_codename = forms.CharField(required=False)
    credit_card_brand_code = forms.CharField(required=False)
    credit_card_id = forms.CharField(required=False)
    channel = forms.CharField(required=False)
    channel_country = forms.CharField(required=False)
    geoip_country = forms.CharField(required=False)
    signature = forms.CharField(required=True)

    def __init__(self, payment, pin, **kwargs):
        super().__init__(**kwargs)
        self.pin = pin
        self.payment = payment

    def clean(self):
        cleaned_data = super().clean()
        if not self.errors:
            key_vars = (
                self.pin,
                cleaned_data.get("id", ""),
                cleaned_data.get("operation_number", ""),
                cleaned_data.get("operation_type", ""),
                cleaned_data.get("operation_status", ""),
                cleaned_data.get("operation_amount", ""),
                cleaned_data.get("operation_currency", ""),
                cleaned_data.get("operation_withdrawal_amount", ""),
                cleaned_data.get("operation_commission_amount", ""),
                cleaned_data.get("is_completed", ""),
                cleaned_data.get("operation_original_amount", ""),
                cleaned_data.get("operation_original_currency", ""),
                cleaned_data.get("operation_datetime", ""),
                cleaned_data.get("operation_related_number", ""),
                cleaned_data.get("control", ""),
                cleaned_data.get("description", ""),
                cleaned_data.get("email", ""),
                cleaned_data.get("p_info", ""),
                cleaned_data.get("p_email", ""),
                cleaned_data.get("credit_card_issuer_identification_number", ""),
                cleaned_data.get("credit_card_masked_number", ""),
                cleaned_data.get("credit_card_brand_codename", ""),
                cleaned_data.get("credit_card_brand_code", ""),
                cleaned_data.get("credit_card_id", ""),
                cleaned_data.get("channel", ""),
                cleaned_data.get("channel_country", ""),
                cleaned_data.get("geoip_country", ""),
            )
            key = "".join(key_vars)
            sha256 = hashlib.sha256()
            sha256.update(key.encode("utf-8"))
            key_hash = sha256.hexdigest()
            if key_hash != self.cleaned_data["signature"]:
                self._errors["signature"] = self.error_class(["Bad hash"])
            if int(cleaned_data["control"]) != self.payment.id:
                self._errors["control"] = self.error_class(["Bad payment id"])
        return cleaned_data

    def save(self, *args, **kwargs):
        status = self.cleaned_data["operation_status"]
        self.payment.transaction_id = self.cleaned_data["operation_number"]
        self.payment.save()
        if status == COMPLETED:
            self.payment.captured_amount = self.payment.total
            self.payment.change_status(PaymentStatus.CONFIRMED)
        elif status == REJECTED:
            self.payment.change_status(PaymentStatus.REJECTED)
