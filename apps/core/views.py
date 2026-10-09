from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.static import serve

from apps.catalog.models import Category, Course


def home(request):
    courses = Course.objects.filter(is_published=True).select_related("category")[:6]
    categories = Category.objects.filter(courses__is_published=True).distinct()
    return render(request, "core/home.html", {"courses": courses, "categories": categories})


def health(request):
    """Used by Docker/Coolify health checks."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error", "db": False}, status=503)
    return JsonResponse({"status": "ok", "db": True})


def public_media(request, path):
    """Serve files under MEDIA_ROOT/public/ (course covers). Protected files never pass here."""
    return serve(request, path, document_root=settings.MEDIA_ROOT)
