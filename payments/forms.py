from django import forms

class PaymentForm(forms.Form):
    '''
    Payment form, suitable for Django templates.
    
    When displaying the form remeber to use *action* and *method*.
    '''
    
    #: Form action URL for template use
    action = ''
    #: Form method for template use, either "get" or "post"
    method = 'post'

    def __init__(self, data, action, method = 'post'):
        super(PaymentForm, self).__init__(auto_id = False)
        self.action = action
        self.method = method
        for key, val in data.items():
            self.fields[key] = forms.CharField(initial=val, widget=forms.widgets.HiddenInput())

