
// Success handler
var successHandler = function(status){
    if (window.console != undefined) {
      console.log("Purchase completed successfully: ", status);
    }
};

// Failure handler
var failureHandler = function(status){
    if (window.console != undefined) {
      console.log("Purchase failed ", status);
    }
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
