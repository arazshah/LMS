"""Brute-force protection for the admin password login."""

from django.contrib.auth.signals import user_login_failed
from django.core.cache import cache
from django.dispatch import receiver
from django.shortcuts import render
from django.urls import reverse

from apps.core.utils import client_ip

MAX_FAILURES = 10
WINDOW_SECONDS = 15 * 60


def _key(request):
    return f"admin-login-failures:{client_ip(request)}"


@receiver(user_login_failed)
def count_failure(sender, credentials, request=None, **kwargs):
    if request is None:
        return
    key = _key(request)
    cache.add(key, 0, WINDOW_SECONDS)
    cache.incr(key)


class AdminLoginThrottleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.method == "POST"
            and request.path == reverse("admin:login")
            and cache.get(_key(request), 0) >= MAX_FAILURES
        ):
            return render(request, "429.html", status=429)
        return self.get_response(request)
