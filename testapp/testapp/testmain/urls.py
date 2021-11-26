from django.urls import path

from testapp.testmain import views

urlpatterns = [
    path("payment-details/<int:payment_id>", views.payment_details),
    path("payment-success", views.payment_success),
    path(
        "payment-failure",
        views.payment_failure,
    ),
    path("", views.create_test_payment),
]
