from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, render

from .models import LiveClass, LiveSession


def live_list(request):
    classes = LiveClass.objects.filter(is_published=True).prefetch_related("sessions")
    return render(request, "live/list.html", {"classes": classes})


def live_detail(request, slug):
    live_class = get_object_or_404(
        LiveClass.objects.filter(is_published=True).prefetch_related(
            Prefetch("sessions", queryset=LiveSession.objects.order_by("starts_at"))
        ),
        slug=slug,
    )
    registered = live_class.is_registered(request.user)
    return render(
        request,
        "live/detail.html",
        {
            "live_class": live_class,
            "sessions": live_class.sessions.all(),
            "registered": registered,
        },
    )
