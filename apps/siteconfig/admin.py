from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse

from .models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("عمومی", {"fields": ("site_name", "tagline", "support_phone", "support_telegram")}),
        (
            "پیامک (sms.ir)",
            {
                "fields": (
                    "sms_api_key",
                    "sms_otp_template_id",
                    "sms_otp_param_name",
                    "sms_paid_template_id",
                    "sms_rejected_template_id",
                    "sms_reminder_template_id",
                ),
                "description": (
                    "برای ورود دانشجوها با کد پیامکی لازم است. در sms.ir یک قالب «ارسال سریع» "
                    "با متنی مثل «کد ورود شما: #CODE#» بسازید و شناسه‌اش را اینجا وارد کنید."
                ),
            },
        ),
        (
            "پرداخت کارت‌به‌کارت",
            {
                "fields": ("card_number", "card_holder", "card_bank"),
                "description": (
                    "خریدار مبلغ را به این کارت واریز می‌کند و تصویر رسید را آپلود می‌کند؛ "
                    "شما در «فروش ← سفارش‌ها» آن را تأیید می‌کنید."
                ),
            },
        ),
        (
            "پرداخت با ربات بله",
            {
                "fields": ("bale_bot_token", "bale_bot_username", "bale_provider_token"),
                "description": (
                    "بعد از ذخیره، دکمه «اتصال ربات بله به سایت» در بالای همین صفحه را بزنید."
                ),
            },
        ),
        ("فاکتور", {"fields": ("seller_name", "seller_phone", "seller_address")}),
    )
    change_form_template = "admin/siteconfig/sitesettings/change_form.html"

    def get_urls(self):
        from django.urls import path

        return [
            path(
                "connect-bale/",
                self.admin_site.admin_view(self.connect_bale),
                name="siteconfig_connect_bale",
            ),
            *super().get_urls(),
        ]

    def connect_bale(self, request):
        from django.contrib import messages

        from apps.shop import bale

        if request.method != "POST":
            return redirect(reverse("admin:siteconfig_sitesettings_change", args=[1]))
        config = SiteSettings.load()
        url = request.build_absolute_uri(
            reverse("shop:bale_webhook", args=[config.bale_webhook_secret])
        )
        try:
            bale.set_webhook(url)
        except bale.BaleError as exc:
            messages.error(request, f"اتصال ربات ناموفق بود: {exc}")
        else:
            messages.success(request, "ربات بله به سایت متصل شد.")
        return redirect(reverse("admin:siteconfig_sitesettings_change", args=[1]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        SiteSettings.load()
        return redirect(reverse("admin:siteconfig_sitesettings_change", args=[1]))
