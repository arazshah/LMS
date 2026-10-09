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
                    "sms_answer_template_id",
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
                "fields": ("bale_bot_token", "bale_bot_username", "bale_provider_token", "bale_welcome_message"),
                "description": (
                    "۱. توکن ربات و نام کاربری ربات را از @botfather در بله بگیرید و وارد کنید.\n"
                    "۲. تنظیمات را ذخیره کنید.\n"
                    "۳. دکمه «اتصال ربات بله» در بالای این صفحه را بزنید تا webhook ثبت شود.\n"
                    "بدون این مرحله ربات پیام دریافت نمی‌کند!\n\n"
                    "«توکن درگاه پرداخت» اختیاری است — بدون آن ربات اطلاعات کارت‌به‌کارت را می‌فرستد."
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
            path(
                "bale-status/",
                self.admin_site.admin_view(self.bale_status),
                name="siteconfig_bale_status",
            ),
            *super().get_urls(),
        ]

    def connect_bale(self, request):
        from django.contrib import messages

        from apps.shop import bale

        if request.method != "POST":
            return redirect(reverse("admin:siteconfig_sitesettings_change", args=[1]))
        config = SiteSettings.load()
        if not config.bale_bot_token:
            messages.error(request, "ابتدا توکن ربات بله را وارد و ذخیره کنید.")
            return redirect(reverse("admin:siteconfig_sitesettings_change", args=[1]))

        # Build the webhook URL — prefer HTTPS and use the request's host
        path = reverse("shop:bale_webhook", args=[config.bale_webhook_secret])
        # Force HTTPS for production (Bale requires HTTPS webhooks)
        scheme = "https"
        host = request.get_host()
        url = f"{scheme}://{host}{path}"
        try:
            bale.set_webhook(url)
        except bale.BaleError as exc:
            messages.error(request, f"اتصال ربات ناموفق بود: {exc}")
        else:
            messages.success(
                request,
                f"✅ ربات بله به سایت متصل شد. آدرس webhook: {url}",
            )
        return redirect(reverse("admin:siteconfig_sitesettings_change", args=[1]))

    def bale_status(self, request):
        from django.contrib import messages
        from django.http import HttpResponse

        from apps.shop import bale

        config = SiteSettings.load()
        if not config.bale_bot_token:
            messages.warning(request, "توکن ربات بله تنظیم نشده است.")
            return redirect(reverse("admin:siteconfig_sitesettings_change", args=[1]))
        try:
            result = bale.call("getWebhookInfo", {})
            url = result.get("url") or "(ثبت نشده)"
            pending = result.get("pending_update_count", 0)
            last_error = result.get("last_error_message") or ""
            msg = f"Webhook URL: {url} | Pending: {pending}"
            if last_error:
                msg += f" | آخرین خطا: {last_error}"
                messages.warning(request, msg)
            else:
                messages.success(request, msg)
        except bale.BaleError as exc:
            messages.error(request, f"خطا در بررسی وضعیت: {exc}")
        return redirect(reverse("admin:siteconfig_sitesettings_change", args=[1]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        SiteSettings.load()
        return redirect(reverse("admin:siteconfig_sitesettings_change", args=[1]))
