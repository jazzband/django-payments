
// Success handler
var successHandler = function(status){
    if (window.console != undefined) {
        console.log("Purchase completed successfully: ", status);
    }
    window.location = $('input#google-wallet-id').data('success-url');
};

// Failure handler
var failureHandler = function(status){
    if (window.console != undefined) {
        console.log("Purchase failed ", status);
    }
    window.location = $('input#google-wallet-id').data('failure-url');
};

function purchase() {
    var generated_jwt = $('input#google-wallet-id').data('jwt');

    google.payments.inapp.buy({
      'jwt'     : generated_jwt,
      'success' : successHandler,
      'failure' : failureHandler
    });
    return false
}

jQuery(document).ready(function() {
    purchase();
});
