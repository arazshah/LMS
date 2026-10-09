import posixpath

from django.conf import settings
from django.db import connection
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.static import serve

from apps.catalog.models import Category, Course
from apps.live.models import LiveClass


def home(request):
    courses = Course.objects.filter(is_published=True).select_related("category")[:6]
    categories = Category.objects.filter(courses__is_published=True).distinct()
    live_classes = LiveClass.objects.filter(is_published=True).prefetch_related("sessions")[:3]
    return render(
        request,
        "core/home.html",
        {"courses": courses, "categories": categories, "live_classes": live_classes},
    )


def health(request):
    """Used by Docker/Coolify health checks."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error", "db": False}, status=503)
    return JsonResponse({"status": "ok", "db": True})


def public_media(request, path):
    """Serve files under MEDIA_ROOT/public/ (course covers) and nothing else.

    `serve` normalises the path, so "public/../protected/x" would escape into
    protected files; reject any path that does not stay inside public/.
    """
    normalized = posixpath.normpath(path)
    if ".." in path.split("/") or not normalized.startswith("public/"):
        raise Http404
    return serve(request, normalized, document_root=settings.MEDIA_ROOT)


def robots_txt(request):
    lines = [
        "User-agent: *",
        # Private, per-user pages; the admin path is deliberately not listed.
        "Disallow: /accounts/",
        "Disallow: /orders/",
        "Disallow: /checkout/",
        "Disallow: /my-courses/",
        "Disallow: /files/",
        "Disallow: /videos/",
        "Disallow: /payments/",
        f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")
