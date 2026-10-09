from django.apps import AppConfig


class VideosConfig(AppConfig):
    name = "apps.videos"
    verbose_name = "ویدیوها"

    def ready(self):
        from . import signals  # noqa: F401
