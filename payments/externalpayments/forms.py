from django.utils.translation import ugettext_lazy as _
from django import forms

from ..forms import PaymentForm

class OrderIdForm(PaymentForm):
    # only shown, return is ignored
    order = forms.CharField(widget=forms.TextInput(attrs={'readonly':'readonly'}),\
                            label=_("Please supply as reference"))


class IBANBankingForm(PaymentForm):
    # only shown, return is ignored
    iban = forms.CharField(widget=forms.TextInput(attrs={'readonly':'readonly'}), label="IBAN")
    bic = forms.CharField(widget=forms.TextInput(attrs={'readonly':'readonly'}), label="BIC")
    order = forms.CharField(widget=forms.TextInput(attrs={'readonly':'readonly'}),\
                                                   label=_("Please supply as reference"))
