from __future__ import unicode_literals
import hashlib

from django import forms


NO_MORE_CONFIRMATION = 0
NEW = 1
ACCEPTED = 2
REJECTED = 3
CANCELED = 4

STATUS_CHOICES = map(lambda c: (c, c), (
    NO_MORE_CONFIRMATION,
    NEW,
    ACCEPTED,
    REJECTED,
    CANCELED
))


class ProcessPaymentForm(forms.Form):

    status = forms.ChoiceField(choices=(('OK', 'OK'), ('FAIL', 'FAIL')))
    id = forms.IntegerField()
    control = forms.IntegerField()
    t_id = forms.CharField()
    amount = forms.DecimalField()
    email = forms.EmailField(required=False)
    t_status = forms.TypedChoiceField(coerce=int, choices=STATUS_CHOICES)
    description = forms.CharField(required=False)
    md5 = forms.CharField()

    def __init__(self, payment, pin, **kwargs):
        super(ProcessPaymentForm, self).__init__(**kwargs)
        self.pin = pin
        self.payment = payment

    def clean(self):
        cleaned_data = super(ProcessPaymentForm, self).clean()
        if not self.errors:
            key_vars = (
                self.pin,
                str(cleaned_data['id']),
                str(cleaned_data['control']),
                str(cleaned_data['t_id']),
                str(cleaned_data['amount']),
                cleaned_data.get('email', ''),
                '',  # service
                '',  # code
                '',  # username
                '',  # password
                str(cleaned_data['t_status']))
            key = ':'.join(key_vars)
            md5 = hashlib.md5()
            md5.update(key.encode('utf-8'))
            key_hash = md5.hexdigest()
            if key_hash != self.cleaned_data['md5']:
                self._errors['md5'] = self.error_class(['Bad hash'])
            if cleaned_data['control'] != self.payment.id:
                self._errors['control'] = self.error_class(['Bad payment id'])
        return cleaned_data

    def save(self, *args, **kwargs):
        status = self.cleaned_data['t_status']
        self.payment.transaction_id = self.cleaned_data['t_id']
        self.payment.save()
        payment_status = self.payment.status
        if status == ACCEPTED:
            self.payment.captured_amount = self.payment.total
            self.payment.change_status('confirmed')
        elif ((status == NO_MORE_CONFIRMATION and payment_status == 'waiting')
              or status == REJECTED or status == CANCELED):
            self.payment.change_status('rejected')
