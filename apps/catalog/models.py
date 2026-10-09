import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


def _unique_slug(instance, value):
    base = slugify(value, allow_unicode=True)[:80] or "item"
    slug, n = base, 2
    model = type(instance)
    while model.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def cover_upload_to(instance, filename):
    return f"public/covers/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


def lesson_file_upload_to(instance, filename):
    # Stored outside public/ so it is only reachable through the access-checked view.
    return f"protected/lessons/{uuid.uuid4().hex}/{Path(filename).name}"


class Category(models.Model):
    title = models.CharField("عنوان", max_length=100)
    slug = models.SlugField("نامک", max_length=100, unique=True, allow_unicode=True, blank=True)
    description = models.TextField("توضیح", blank=True)
    order = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name = "دسته"
        verbose_name_plural = "دسته‌ها"
        ordering = ["order", "title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.title)
        super().save(*args, **kwargs)


class Course(models.Model):
    class Level(models.TextChoices):
        BEGINNER = "beginner", "مقدماتی"
        INTERMEDIATE = "intermediate", "متوسط"
        ADVANCED = "advanced", "پیشرفته"

    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="courses", verbose_name="دسته"
    )
    title = models.CharField("عنوان", max_length=200)
    slug = models.SlugField("نامک", max_length=100, unique=True, allow_unicode=True, blank=True)
    summary = models.CharField("خلاصه", max_length=300, blank=True)
    description = models.TextField("توضیحات", blank=True)
    cover = models.ImageField("تصویر جلد", upload_to=cover_upload_to, blank=True)
    level = models.CharField("سطح", max_length=20, choices=Level, default=Level.BEGINNER)
    prerequisites = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="required_by", verbose_name="پیش‌نیازها"
    )
    price = models.PositiveIntegerField("قیمت (تومان)", default=0, help_text="۰ یعنی رایگان")
    access_days = models.PositiveIntegerField(
        "مدت دسترسی (روز)", null=True, blank=True, default=365, help_text="خالی = دائمی"
    )
    is_published = models.BooleanField("منتشر شده", default=False)
    order = models.PositiveIntegerField("ترتیب", default=0)
    created_at = models.DateTimeField("ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("ویرایش", auto_now=True)

    class Meta:
        verbose_name = "دوره"
        verbose_name_plural = "دوره‌ها"
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalog:course_detail", args=[self.slug])

    @property
    def is_free(self):
        return self.price == 0

    def published_lessons(self):
        return Lesson.objects.filter(chapter__course=self, is_published=True).order_by(
            "chapter__order", "chapter__id", "order", "id"
        )

    def has_access(self, user):
        if self.is_free:
            return True
        if not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        return Enrollment.objects.active().filter(user=user, course=self).exists()


class Chapter(models.Model):
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="chapters", verbose_name="دوره"
    )
    title = models.CharField("عنوان", max_length=200)
    order = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name = "فصل"
        verbose_name_plural = "فصل‌ها"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.course} / {self.title}"


class Lesson(models.Model):
    class Kind(models.TextChoices):
        VIDEO = "video", "ویدیو"
        DOCUMENT = "document", "PDF / اسلاید"
        NOTEBOOK = "notebook", "نوت‌بوک"
        GEODATA = "geodata", "داده مکانی"
        CODE = "code", "کد"
        TEXT = "text", "متن"

    chapter = models.ForeignKey(
        Chapter, on_delete=models.CASCADE, related_name="lessons", verbose_name="فصل"
    )
    title = models.CharField("عنوان", max_length=200)
    kind = models.CharField("نوع", max_length=20, choices=Kind, default=Kind.VIDEO)
    body = models.TextField("متن / توضیحات", blank=True)
    duration_minutes = models.PositiveIntegerField("مدت (دقیقه)", null=True, blank=True)
    is_free = models.BooleanField("رایگان (پیش‌نمایش)", default=False)
    is_published = models.BooleanField("منتشر شده", default=True)
    order = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name = "جلسه"
        verbose_name_plural = "جلسه‌ها"
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("catalog:lesson_detail", args=[self.course.slug, self.pk])

    @property
    def course(self):
        return self.chapter.course

    def can_view(self, user):
        return self.is_free or self.course.has_access(user)


class LessonFile(models.Model):
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name="files", verbose_name="جلسه"
    )
    title = models.CharField("عنوان", max_length=200)
    file = models.FileField("فایل", upload_to=lesson_file_upload_to, max_length=255)
    order = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name = "فایل جلسه"
        verbose_name_plural = "فایل‌های جلسه"
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("catalog:lesson_file", args=[self.pk])

    @property
    def filename(self):
        return Path(self.file.name).name


class EnrollmentQuerySet(models.QuerySet):
    def active(self):
        now = timezone.now()
        return self.filter(starts_at__lte=now).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )


class Enrollment(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "دستی (ادمین)"
        ORDER = "order", "خرید"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name="کاربر",
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="enrollments", verbose_name="دوره"
    )
    starts_at = models.DateTimeField("شروع دسترسی", default=timezone.now)
    expires_at = models.DateTimeField(
        "پایان دسترسی",
        null=True,
        blank=True,
        help_text="اگر خالی بماند، طبق «مدت دسترسی» دوره محاسبه می‌شود (یا دائمی).",
    )
    source = models.CharField("منبع", max_length=20, choices=Source, default=Source.MANUAL)
    order = models.ForeignKey(
        "shop.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrollments",
        verbose_name="سفارش",
    )
    note = models.CharField("یادداشت", max_length=255, blank=True)
    created_at = models.DateTimeField("ایجاد", auto_now_add=True)

    objects = EnrollmentQuerySet.as_manager()

    class Meta:
        verbose_name = "دسترسی دوره"
        verbose_name_plural = "دسترسی‌های دوره"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} ← {self.course}"

    def save(self, *args, **kwargs):
        if self._state.adding and self.expires_at is None and self.course.access_days:
            self.expires_at = self.starts_at + timedelta(days=self.course.access_days)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        now = timezone.now()
        return self.starts_at <= now and (self.expires_at is None or self.expires_at > now)
