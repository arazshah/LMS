from django.urls import path

from . import views

app_name = "videos"

urlpatterns = [
    path("videos/<int:lesson_id>/<path:path>", views.hls, name="hls"),
]
