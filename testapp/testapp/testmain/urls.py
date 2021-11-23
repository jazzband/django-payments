from django.urls import path

from testapp.testmain import views

urlpatterns = [path("payment-details/<int:payment_id>", views.payment_details)]
