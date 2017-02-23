document.addEventListener('DOMContentLoaded', function () {
    var stripeInput = document.getElementById('id_stripe_token');
    var form = stripeInput.form;
    var publishableKey = stripeInput.attributes['data-publishable-key'].value;
    Stripe.setPublishableKey(publishableKey);
    form.addEventListener('submit', function (e) {
        var button = this.querySelector('[type=submit]');
        button.disabled = true;
        Stripe.card.createToken({
            name: this.elements['name'].value,
            number: this.elements['number'].value,
            cvc: this.elements['cvv2'].value,
            exp_month: this.elements['expiration_0'].value,
            exp_year: this.elements['expiration_1'].value
        }, function (status, response) {
            if (400 <= status && status <= 500) {
                alert(response.error.message);
                button.disabled = false;
            } else {
                stripeInput.value = response.id;
                form.submit();
            }
        });
        e.preventDefault();
    }, false);
}, false);
