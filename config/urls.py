from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path

from apps.core.sitemaps import SITEMAPS
from apps.core.views import public_media
from apps.shop.reports import sales_report

admin.site.site_header = "مدیریت LMS"
admin.site.site_title = "مدیریت LMS"
admin.site.index_title = "پنل مدیریت"

urlpatterns = [
    path(f"{settings.ADMIN_URL}reports/", sales_report, name="admin_sales_report"),
    path(settings.ADMIN_URL, admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.videos.urls")),
    path("", include("apps.shop.urls")),
    path("", include("apps.live.urls")),
    path("", include("apps.qa.urls")),
    path("", include("apps.core.urls")),
    # Only media/public/ (e.g. course covers) is served directly; protected files go
    # through access-checked views.
    re_path(r"^media/(?P<path>public/.+)$", public_media, name="public_media"),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
]
