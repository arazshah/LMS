from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from apps.core.views import public_media

admin.site.site_header = "مدیریت LMS"
admin.site.site_title = "مدیریت LMS"
admin.site.index_title = "پنل مدیریت"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.core.urls")),
    # Only media/public/ (e.g. course covers) is served directly; protected files go
    # through access-checked views.
    re_path(r"^media/(?P<path>public/.+)$", public_media, name="public_media"),
]
