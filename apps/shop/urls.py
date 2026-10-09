from django.urls import path

from . import views

app_name = "shop"

urlpatterns = [
    path("bundles/", views.bundle_list, name="bundle_list"),
    path("bundles/<str:slug>/", views.bundle_detail, name="bundle_detail"),
    path("checkout/<str:kind>/<str:slug>/", views.checkout, name="checkout"),
    path("orders/", views.order_list, name="order_list"),
    path("orders/<str:number>/", views.order_pay, name="order_pay"),
    path("orders/<str:number>/status/", views.order_status, name="order_status"),
    path("orders/<str:number>/invoice.pdf", views.order_invoice, name="order_invoice"),
    path("orders/<str:number>/receipt/", views.order_receipt, name="order_receipt"),
    path("payments/bale/<str:secret>/", views.bale_webhook, name="bale_webhook"),
]
