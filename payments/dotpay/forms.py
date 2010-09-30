# -*- coding:utf-8 -*-
from django import forms
from django.utils.translation import ugettext as _
from django.db.models import Q

import md5

from ..models import Payment

NO_MORE_CONFIRMATION=0
NEW=1
ACCEPTED=2
REJECTED=3
CANCELED=4

STATUS_CHOICES = map(lambda c: (c,c), (
    NO_MORE_CONFIRMATION,
    NEW,
    ACCEPTED,
    REJECTED,
    CANCELED
))

class ProcessPaymentForm(forms.Form):
    status = forms.ChoiceField(choices=(("OK","OK"),("FAIL","FAIL")))
    id = forms.IntegerField()
    #this should be Payments modelchoicefield
    control = forms.IntegerField()
    #control = forms.TypedChoiceField(
    #    choices = [ (id,id) for id in Payment.objects.exclude(
    #            Q(status='rejected')
    #        ).values_list("id", flat=True)
    #    ],
    #    coerce=int,
    #)
    t_id = forms.CharField()
    amount = forms.DecimalField()
    email = forms.EmailField(required=False)
    t_status = forms.TypedChoiceField(coerce=int, choices=STATUS_CHOICES)
    description = forms.CharField(required=False)
    md5 = forms.CharField()

    def __init__(self, pin, **kwargs):
        super(ProcessPaymentForm, self).__init__(**kwargs)
        self.pin = pin

    def clean(self):
        vars = {
            "pin": self.pin,
            "id": self.cleaned_data['id'],
            "control": self.cleaned_data["control"],
            "t_id": self.cleaned_data["t_id"],
            "amount": self.cleaned_data["amount"],
            "email": self.cleaned_data.get("email", ""),
            "service": "",
            "code": "",
            "username": "",
            "password": "",
            "t_status": self.cleaned_data["t_status"]
        }

        key = "%(pin)s:%(id)s:%(control)s:%(t_id)s:%(amount)s:%(email)s:%(service)s:%(code)s:%(username)s:%(password)s:%(t_status)s" % vars
        hash = md5.new(key).hexdigest()
        if hash != self.cleaned_data["md5"]:
            raise forms.ValidationError()
        return self.cleaned_data

    def save(self, *args, **kwargs):
        payment_id = self.cleaned_data['control']
        status = self.cleaned_data['t_status']

        payment = Payment.objects.get(id=payment_id)
        payment.transaction_id = self.cleaned_data['t_id']
        payment.save()

        if status == ACCEPTED:
            payment.change_status('confirmed')
        elif (status == NO_MORE_CONFIRMATION and payment.status == 'waiting') \
          or status == REJECTED or status == CANCELED:
            payment.change_status('rejected')
