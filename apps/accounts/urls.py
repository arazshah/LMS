from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_phone, name="login"),
    path("login/verify/", views.login_verify, name="verify"),
    path("profile/", views.profile, name="profile"),
    path("logout/", views.logout_view, name="logout"),
]
