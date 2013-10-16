(function() {

    function purchase() {
        var stripe_input = document.getElementById('stripe-id');

        var token = function(result){
            stripe_input.value = result.id;
            stripe_input.form.submit();
        };

        StripeCheckout.open({
            key: stripe_input.getAttribute('data-key'),
            address: false,
            amount: stripe_input.getAttribute('data-amount'),
            currency: stripe_input.getAttribute('data-currency'),
            name: stripe_input.getAttribute('data-name'),
            description: stripe_input.getAttribute('data-description'),
            panelLabel: 'Checkout',
            token: token
        });

        return false;
    }

    $ = this.jQuery || this.Zepto || this.ender || this.$;

    if($) {
        $(purchase);
    } else {
        window.onload = purchase;
    }
})();
