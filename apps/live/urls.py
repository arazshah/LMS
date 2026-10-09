from django.urls import path

from . import views

app_name = "live"

urlpatterns = [
    path("live/", views.live_list, name="list"),
    path("live/<str:slug>/", views.live_detail, name="detail"),
]
