import pytest
from django.core.exceptions import ValidationError

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
