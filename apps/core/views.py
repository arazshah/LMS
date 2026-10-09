from django.db import connection
from django.http import JsonResponse
from django.views.generic import TemplateView


class HomeView(TemplateView):
    template_name = "core/home.html"


def health(request):
    """Used by Docker/Coolify health checks."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error", "db": False}, status=503)
    return JsonResponse({"status": "ok", "db": True})
