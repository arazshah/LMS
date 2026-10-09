import shutil
import uuid
from pathlib import Path

from django.conf import settings
from django.db import models


def source_upload_to(instance, filename):
    return f"protected/videos/{instance.uid.hex}/source{Path(filename).suffix.lower()}"


class LessonVideo(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در صف تبدیل"
        PROCESSING = "processing", "در حال تبدیل"
        READY = "ready", "آماده پخش"
        FAILED = "failed", "خطا"

    lesson = models.OneToOneField(
        "catalog.Lesson", on_delete=models.CASCADE, related_name="video", verbose_name="جلسه"
    )
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    source = models.FileField("فایل اصلی", upload_to=source_upload_to, max_length=255, blank=True)
    original_name = models.CharField("نام فایل", max_length=255, blank=True)
    size_bytes = models.BigIntegerField("حجم فایل اصلی", default=0)
    status = models.CharField("وضعیت", max_length=20, choices=Status, default=Status.PENDING)
    duration_seconds = models.PositiveIntegerField("مدت (ثانیه)", null=True, blank=True)
    renditions = models.CharField("کیفیت‌ها", max_length=100, blank=True)
    error = models.TextField("خطا", blank=True)
    created_at = models.DateTimeField("آپلود", auto_now_add=True)
    updated_at = models.DateTimeField("به‌روزرسانی", auto_now=True)

    class Meta:
        verbose_name = "ویدیو"
        verbose_name_plural = "ویدیوها"

    def __str__(self):
        return f"ویدیوی {self.lesson}"

    @property
    def hls_dir(self) -> Path:
        return Path(settings.MEDIA_ROOT) / "protected" / "hls" / self.uid.hex

    @property
    def is_ready(self):
        return self.status == self.Status.READY

    def delete_files(self):
        if self.source:
            self.source.delete(save=False)
        shutil.rmtree(self.hls_dir, ignore_errors=True)
        source_dir = Path(settings.MEDIA_ROOT) / "protected" / "videos" / self.uid.hex
        shutil.rmtree(source_dir, ignore_errors=True)
