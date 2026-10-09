from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    verbose_name = "کاربران"

    def ready(self):
        from . import throttle  # noqa: F401  (registers the login-failure signal)
