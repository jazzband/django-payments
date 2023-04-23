document.addEventListener('DOMContentLoaded', function () {
    console.log("hello there DOMContentLoaded")
    const stripeInput = document.getElementById('id_stripe_token');
    const stripe_session_id = document.getElementById('session_id');
    const form = stripeInput.form;
    const publishableKey = stripeInput.attributes['data-publishable-key'].value;
    const stripe = Stripe(publishableKey)

    form.addEventListener('submit', function (e) {
        console.log("hello there submit")
        var button = this.querySelector('[type=submit]');
        button.disabled = true;
        stripe.redirectToCheckout({ sessionId: stripe_session_id })
        e.preventDefault();
    }, false);
}, false);
console.log("hello there stripe.js")