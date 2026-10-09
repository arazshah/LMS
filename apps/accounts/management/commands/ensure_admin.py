import os

from django.core.management.base import BaseCommand

from apps.accounts.models import User

DEFAULT_PHONE = "09120000000"
DEFAULT_PASSWORD = "admin12345"


class Command(BaseCommand):
    help = "Create the initial admin on first deploy (only if no superuser exists)."

    def handle(self, *args, **options):
        if User.objects.filter(is_superuser=True).exists():
            return
        phone = os.environ.get("DJANGO_ADMIN_PHONE") or DEFAULT_PHONE
        password = os.environ.get("DJANGO_ADMIN_PASSWORD") or DEFAULT_PASSWORD
        user = User.objects.create_superuser(phone, password, first_name="مدیر")
        user.must_change_password = True
        user.save(update_fields=["must_change_password"])
        self.stdout.write(f"Created initial admin {user.phone}; password change required.")
