document.addEventListener('DOMContentLoaded', function () {
    var stripeInput = document.getElementById('id_stripe_token');
    var form = stripeInput.form;
    var publishableKey = stripeInput.attributes['data-publishable-key'].value;
    Stripe.setPublishableKey(publishableKey);
    form.addEventListener('submit', function (e) {
        var button = this.querySelector('[type=submit]');
        button.disabled = true;
        Stripe.card.createToken({
            name: this.elements.id_name.value,
            number: this.elements.id_number.value,
            cvc: this.elements.id_cvv2.value,
            exp_month: this.elements.id_expiration_0.value,
            exp_year: this.elements.id_expiration_1.value,
            address_line1: stripeInput.attributes['data-address-line1'].value,
            address_line2: stripeInput.attributes['data-address-line2'].value,
            address_city: stripeInput.attributes['data-address-city'].value,
            address_state: stripeInput.attributes['data-address-state'].value,
            address_zip: stripeInput.attributes['data-address-zip'].value,
            address_country: stripeInput.attributes['data-address-country'].value
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