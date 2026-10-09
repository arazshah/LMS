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
                "fields": ("sms_api_key", "sms_otp_template_id", "sms_otp_param_name"),
                "description": (
                    "برای ورود دانشجوها با کد پیامکی لازم است. در sms.ir یک قالب «ارسال سریع» "
                    "با متنی مثل «کد ورود شما: #CODE#» بسازید و شناسه‌اش را اینجا وارد کنید."
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        SiteSettings.load()
        return redirect(reverse("admin:siteconfig_sitesettings_change", args=[1]))
