def client_ip(request):
    # Coolify's proxy sets X-Real-IP; the app is only reachable through it.
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR")
