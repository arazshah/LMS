from django.conf import settings
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "مدیریت LMS"
admin.site.site_title = "مدیریت LMS"
admin.site.index_title = "پنل مدیریت"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("apps.core.urls")),
]
