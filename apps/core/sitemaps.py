from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.catalog.models import Course
from apps.live.models import LiveClass
from apps.shop.models import Bundle


class StaticSitemap(Sitemap):
    changefreq = "weekly"

    def items(self):
        return ["core:home", "catalog:course_list", "shop:bundle_list", "live:list"]

    def location(self, item):
        return reverse(item)


class CourseSitemap(Sitemap):
    changefreq = "weekly"

    def items(self):
        return Course.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.updated_at


class BundleSitemap(Sitemap):
    def items(self):
        return Bundle.objects.filter(is_published=True)


class LiveClassSitemap(Sitemap):
    def items(self):
        return LiveClass.objects.filter(is_published=True)


SITEMAPS = {
    "static": StaticSitemap,
    "courses": CourseSitemap,
    "bundles": BundleSitemap,
    "live": LiveClassSitemap,
}
