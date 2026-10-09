from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("courses/", views.course_list, name="course_list"),
    path("courses/<str:slug>/", views.course_detail, name="course_detail"),
    path(
        "courses/<str:course_slug>/lessons/<int:lesson_id>/",
        views.lesson_detail,
        name="lesson_detail",
    ),
    path("files/<int:file_id>/", views.lesson_file, name="lesson_file"),
    path("my-courses/", views.my_courses, name="my_courses"),
]
