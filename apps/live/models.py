from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import _unique_slug, cover_upload_to

JOIN_WINDOW = timedelta(minutes=15)


class LiveClass(models.Model):
    title = models.CharField("عنوان", max_length=200)
    slug = models.SlugField("نامک", max_length=100, unique=True, allow_unicode=True, blank=True)
    summary = models.CharField("خلاصه", max_length=300, blank=True)
    description = models.TextField("توضیحات", blank=True)
    cover = models.ImageField("تصویر جلد", upload_to=cover_upload_to, blank=True)
    price = models.PositiveIntegerField("قیمت (تومان)")
    capacity = models.PositiveIntegerField(
        "ظرفیت", null=True, blank=True, help_text="خالی = نامحدود"
    )
    is_published = models.BooleanField("منتشر شده", default=False)
    order = models.PositiveIntegerField("ترتیب", default=0)
    created_at = models.DateTimeField("ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "کلاس زنده"
        verbose_name_plural = "کلاس‌های زنده"
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("live:detail", args=[self.slug])

    @property
    def seats_taken(self):
        return self.registrations.count()

    @property
    def is_full(self):
        return self.capacity is not None and self.seats_taken >= self.capacity

    @property
    def seats_left(self):
        return None if self.capacity is None else max(0, self.capacity - self.seats_taken)

    def upcoming_sessions(self):
        return self.sessions.filter(starts_at__gte=timezone.now() - timedelta(hours=4))

    def next_session(self):
        now = timezone.now()
        for session in self.sessions.all():
            if session.ends_at > now:
                return session
        return None

    def is_registered(self, user):
        if not user.is_authenticated:
            return False
        return user.is_staff or self.registrations.filter(user=user).exists()


class LiveSession(models.Model):
    live_class = models.ForeignKey(
        LiveClass, on_delete=models.CASCADE, related_name="sessions", verbose_name="کلاس"
    )
    title = models.CharField("عنوان جلسه", max_length=200)
    starts_at = models.DateTimeField("زمان شروع")
    duration_minutes = models.PositiveIntegerField("مدت (دقیقه)", default=90)
    meet_link = models.URLField("لینک Google Meet", blank=True)
    notes = models.TextField("توضیحات", blank=True)
    reminder_day_sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    reminder_hour_sent_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "جلسه زنده"
        verbose_name_plural = "جلسه‌های زنده"
        ordering = ["starts_at"]

    def __str__(self):
        return f"{self.live_class} — {self.title}"

    @property
    def ends_at(self):
        return self.starts_at + timedelta(minutes=self.duration_minutes)

    @property
    def is_joinable(self):
        now = timezone.now()
        return bool(self.meet_link) and self.starts_at - JOIN_WINDOW <= now <= self.ends_at

    @property
    def is_over(self):
        return timezone.now() > self.ends_at


class LiveRegistration(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="live_registrations",
        verbose_name="کاربر",
    )
    live_class = models.ForeignKey(
        LiveClass, on_delete=models.CASCADE, related_name="registrations", verbose_name="کلاس"
    )
    order = models.ForeignKey(
        "shop.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="live_registrations",
        verbose_name="سفارش",
    )
    note = models.CharField("یادداشت", max_length=255, blank=True)
    created_at = models.DateTimeField("ثبت‌نام", auto_now_add=True)

    class Meta:
        verbose_name = "ثبت‌نام کلاس زنده"
        verbose_name_plural = "ثبت‌نام‌های کلاس زنده"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "live_class"], name="one_registration_per_user")
        ]

    def __str__(self):
        return f"{self.user} ← {self.live_class}"
