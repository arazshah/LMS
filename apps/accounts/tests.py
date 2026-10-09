import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from .models import User
from .phone import normalize_phone


@pytest.mark.parametrize(
    "raw",
    [
        "09121234567",
        "+989121234567",
        "00989121234567",
        "989121234567",
        "9121234567",
        "۰۹۱۲۱۲۳۴۵۶۷",
        "0912 123 4567",
        "0912-123-4567",
    ],
)
def test_normalize_phone_accepts_common_formats(raw):
    assert normalize_phone(raw) == "09121234567"


@pytest.mark.parametrize("raw", ["", "0912123456", "091212345678", "02112345678", "abc"])
def test_normalize_phone_rejects_invalid(raw):
    with pytest.raises(ValidationError):
        normalize_phone(raw)


@pytest.mark.django_db
def test_create_user_normalizes_phone_and_has_no_password():
    user = User.objects.create_user("+989121234567")
    assert user.phone == "09121234567"
    assert not user.has_usable_password()
    assert not user.is_staff


@pytest.mark.django_db
def test_create_superuser_requires_password():
    with pytest.raises(ValueError):
        User.objects.create_superuser("09121234567")
    admin = User.objects.create_superuser("09121234567", "s3cret-pass")
    assert admin.is_staff and admin.is_superuser
    assert admin.check_password("s3cret-pass")


@pytest.mark.django_db
def test_ensure_admin_creates_admin_once_with_forced_password_change():
    call_command("ensure_admin")
    admin = User.objects.get(is_superuser=True)
    assert admin.phone == "09120000000"
    assert admin.check_password("admin12345")
    assert admin.must_change_password

    admin.set_password("a-new-strong-password")
    admin.save()
    call_command("ensure_admin")
    assert User.objects.filter(is_superuser=True).count() == 1
    admin.refresh_from_db()
    assert admin.check_password("a-new-strong-password")
    assert not admin.must_change_password


@pytest.mark.django_db
def test_user_with_must_change_password_is_kept_on_password_change(client, settings):
    call_command("ensure_admin")
    assert client.login(phone="09120000000", password="admin12345")
    change_url = reverse("admin:password_change")

    response = client.get(f"/{settings.ADMIN_URL}")
    assert response.status_code == 302
    assert response.url == change_url

    response = client.post(
        change_url,
        {
            "old_password": "admin12345",
            "new_password1": "Geo-AI-strong-2026",
            "new_password2": "Geo-AI-strong-2026",
        },
    )
    assert response.status_code == 302
    assert client.get(f"/{settings.ADMIN_URL}").status_code == 200
