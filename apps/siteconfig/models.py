from django.core.cache import cache
from django.db import models

CACHE_KEY = "siteconfig:settings"


class SiteSettings(models.Model):
    """Single row of settings the admin edits from the panel (no env vars needed)."""

    site_name = models.CharField("نام سایت", max_length=100, default="آموزش هوش مصنوعی مکانی")
    tagline = models.CharField(
        "شعار",
        max_length=200,
        blank=True,
        default="دوره‌های تخصصی GeoAI، سنجش از دور و تحلیل داده‌های مکانی",
    )
    support_phone = models.CharField("تلفن پشتیبانی", max_length=20, blank=True)
    support_telegram = models.CharField(
        "تلگرام/بله پشتیبانی", max_length=100, blank=True, help_text="مثلاً ‎@username"
    )

    sms_api_key = models.CharField(
        "کلید API sms.ir",
        max_length=200,
        blank=True,
        help_text="از پنل sms.ir، بخش برنامه‌نویسان ← لیست کلیدهای API",
    )
    sms_otp_template_id = models.PositiveIntegerField(
        "شناسه قالب کد ورود", null=True, blank=True, help_text="قالب ارسال سریع (Verify) در sms.ir"
    )
    sms_otp_param_name = models.CharField(
        "نام پارامتر کد در قالب", max_length=50, default="CODE", help_text="مثلاً CODE برای #CODE#"
    )

    class Meta:
        verbose_name = "تنظیمات سایت"
        verbose_name_plural = "تنظیمات سایت"

    def __str__(self):
        return "تنظیمات سایت"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY)

    def delete(self, *args, **kwargs):
        pass

    @property
    def sms_configured(self):
        return bool(self.sms_api_key and self.sms_otp_template_id)

    @classmethod
    def load(cls):
        obj = cache.get(CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY, obj, 300)
        return obj
