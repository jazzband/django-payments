(function() {

    function purchase() {
        var stripe_input = document.getElementById('stripe-id');
        stripe_input.value = '';

        StripeCheckout.open({
            key: stripe_input.getAttribute('data-key'),
            address: false,
            amount: stripe_input.getAttribute('data-amount'),
            currency: stripe_input.getAttribute('data-currency'),
            name: stripe_input.getAttribute('data-name'),
            description: stripe_input.getAttribute('data-description'),
            panelLabel: 'Checkout',
            token: function(result) {
                stripe_input.value = result.id;
            },
            closed: function() {
                stripe_input.form.submit();
            }
        });
    }

    $ = this.jQuery || this.Zepto || this.ender || this.$;

    if($) {
        $(purchase);
    } else {
        window.onload = purchase;
    }
})();
