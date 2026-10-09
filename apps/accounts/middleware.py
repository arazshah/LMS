from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Keep users flagged with must_change_password on the password-change page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.must_change_password:
            allowed = {
                reverse("admin:password_change"),
                reverse("admin:password_change_done"),
                reverse("admin:logout"),
            }
            if request.path not in allowed and not request.path.startswith("/static/"):
                return redirect("admin:password_change")
        return self.get_response(request)
