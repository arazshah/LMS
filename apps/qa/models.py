from django.conf import settings
from django.db import models


class Question(models.Model):
    lesson = models.ForeignKey(
        "catalog.Lesson", on_delete=models.CASCADE, related_name="questions", verbose_name="جلسه"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="پرسنده",
    )
    body = models.TextField("سوال", max_length=3000)
    answer = models.TextField("پاسخ", blank=True)
    answered_at = models.DateTimeField("زمان پاسخ", null=True, blank=True)
    is_hidden = models.BooleanField(
        "مخفی", default=False, help_text="سوال نامناسب یا تکراری برای دانشجوها نمایش داده نشود"
    )
    created_at = models.DateTimeField("زمان سوال", auto_now_add=True)

    class Meta:
        verbose_name = "سوال"
        verbose_name_plural = "سوال‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return self.body[:60]

    @property
    def is_answered(self):
        return bool(self.answer.strip())
