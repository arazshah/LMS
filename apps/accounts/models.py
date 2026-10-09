from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from .phone import normalize_phone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, phone, password=None, **extra_fields):
        user = self.model(phone=normalize_phone(phone), **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not password:
            raise ValueError("Superuser must have a password.")
        return self.create_user(phone, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Students sign in with mobile + SMS code; the admin also has a password."""

    phone = models.CharField("شماره موبایل", max_length=11, unique=True)
    first_name = models.CharField("نام", max_length=100, blank=True)
    last_name = models.CharField("نام خانوادگی", max_length=100, blank=True)
    is_active = models.BooleanField("فعال", default=True)
    is_staff = models.BooleanField("دسترسی مدیریت", default=False)
    date_joined = models.DateTimeField("تاریخ عضویت", default=timezone.now)
    must_change_password = models.BooleanField(
        "الزام به تغییر رمز",
        default=False,
        help_text="کاربر تا رمز خود را عوض نکند به بخش‌های دیگر دسترسی ندارد.",
    )

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"

    def __str__(self):
        return self.get_full_name() or self.phone

    def clean(self):
        super().clean()
        self.phone = normalize_phone(self.phone)

    def set_password(self, raw_password):
        super().set_password(raw_password)
        self.must_change_password = False

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name or self.phone
