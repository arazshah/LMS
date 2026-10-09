import secrets

from django.core.cache import cache
from django.db import models

CACHE_KEY = "siteconfig:settings"


def _new_secret():
    return secrets.token_urlsafe(32)


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

    sms_paid_template_id = models.PositiveIntegerField(
        "قالب پیامک «پرداخت تأیید شد»",
        null=True,
        blank=True,
        help_text="پارامترها: #ORDER# (شماره سفارش) و #TITLE# (نام محصول). خالی = ارسال نشود",
    )
    sms_rejected_template_id = models.PositiveIntegerField(
        "قالب پیامک «رسید تأیید نشد»",
        null=True,
        blank=True,
        help_text="پارامتر: #ORDER# (شماره سفارش). خالی = ارسال نشود",
    )
    sms_reminder_template_id = models.PositiveIntegerField(
        "قالب پیامک «یادآوری کلاس زنده»",
        null=True,
        blank=True,
        help_text="پارامترها: #TITLE# (نام کلاس) و #TIME# (تاریخ و ساعت). خالی = ارسال نشود",
    )

    sms_answer_template_id = models.PositiveIntegerField(
        "قالب پیامک «پاسخ سوال شما داده شد»",
        null=True,
        blank=True,
        help_text="پارامتر: #TITLE# (نام جلسه). خالی = ارسال نشود",
    )

    card_number = models.CharField(
        "شماره کارت (کارت‌به‌کارت)", max_length=30, blank=True, help_text="به خریدار نمایش داده می‌شود"
    )
    card_holder = models.CharField("نام صاحب کارت", max_length=100, blank=True)
    card_bank = models.CharField("نام بانک", max_length=50, blank=True)

    bale_bot_token = models.CharField(
        "توکن ربات بله", max_length=200, blank=True, help_text="از ‎@botfather در بله"
    )
    bale_bot_username = models.CharField(
        "نام کاربری ربات بله", max_length=100, blank=True, help_text="بدون @، مثلاً araz_lms_bot"
    )
    bale_provider_token = models.CharField(
        "توکن درگاه پرداخت بله (provider_token)",
        max_length=100,
        blank=True,
        help_text=(
            "توکن درگاه پرداخت از @BotFather در بله (منوی Bot Payments). "
            "این توکن با شماره کارت فرق دارد. "
            "اگر این فیلد خالی باشد، ربات در صورت خطا آدرس کارت‌به‌کارت را به کاربر می‌دهد."
        ),
    )
    bale_webhook_secret = models.CharField(max_length=64, default=_new_secret, editable=False)

    seller_name = models.CharField(
        "نام فروشنده (روی فاکتور)", max_length=150, blank=True, help_text="خالی = نام سایت"
    )
    seller_phone = models.CharField("تلفن فروشنده (روی فاکتور)", max_length=30, blank=True)
    seller_address = models.CharField("آدرس فروشنده (روی فاکتور)", max_length=300, blank=True)

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

    @property
    def bale_configured(self):
        return bool(self.bale_bot_token and self.bale_bot_username and self.bale_provider_token)

    @property
    def card_configured(self):
        return bool(self.card_number)

    @classmethod
    def load(cls):
        obj = cache.get(CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY, obj, 300)
        return obj
