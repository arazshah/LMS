from django.urls import path

from . import views

app_name = "qa"

urlpatterns = [
    path("lessons/<int:lesson_id>/ask/", views.ask, name="ask"),
]
