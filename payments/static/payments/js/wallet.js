(function() {

    // Success handler
    var successHandler = function(status){
        if (window.console != undefined) {
            console.log("Purchase completed successfully: ", status);
        }
        window.location = document.getElementById('google-wallet-id').getAttribute('data-success-url');
    };

    // Failure handler
    var failureHandler = function(status){
        if (window.console != undefined) {
            console.log("Purchase failed ", status);
        }
        window.location = document.getElementById('google-wallet-id').getAttribute('data-failure-url');
    };

    function purchase() {
        var generated_jwt = document.getElementById('google-wallet-id').getAttribute('data-jwt');

        google.payments.inapp.buy({
            'jwt'     : generated_jwt,
            'success' : successHandler,
            'failure' : failureHandler
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
