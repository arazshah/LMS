from django.contrib import admin
from django.db import models

from apps.core.templatetags.fa import jdate

from .models import LiveClass, LiveRegistration, LiveSession


class LiveSessionInline(admin.TabularInline):
    model = LiveSession
    extra = 1
    fields = ("title", "starts_at", "jalali_start", "duration_minutes", "meet_link")
    readonly_fields = ("jalali_start",)
    # A Meet link pasted without a scheme should become https://...
    formfield_overrides = {models.URLField: {"assume_scheme": "https"}}

    @admin.display(description="تاریخ شمسی")
    def jalali_start(self, obj):
        return jdate(obj.starts_at, "%Y/%m/%d %H:%M") if obj.pk else "—"


class LiveRegistrationInline(admin.TabularInline):
    model = LiveRegistration
    extra = 0
    fields = ("user", "order", "note", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("user",)
    raw_id_fields = ("order",)


@admin.register(LiveClass)
class LiveClassAdmin(admin.ModelAdmin):
    list_display = ("title", "price", "capacity", "seats", "next_session_display", "is_published")
    list_editable = ("is_published",)
    search_fields = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    inlines = [LiveSessionInline, LiveRegistrationInline]
    fieldsets = (
        (None, {"fields": ("title", "slug", "summary", "description", "cover")}),
        ("فروش", {"fields": ("price", "capacity", "is_published", "order")}),
    )

    @admin.display(description="ثبت‌نام‌شده")
    def seats(self, obj):
        return obj.seats_taken

    @admin.display(description="جلسه بعدی")
    def next_session_display(self, obj):
        session = obj.next_session()
        return jdate(session.starts_at, "%Y/%m/%d %H:%M") if session else "—"


@admin.register(LiveRegistration)
class LiveRegistrationAdmin(admin.ModelAdmin):
    list_display = ("user", "live_class", "order", "created_at")
    list_filter = ("live_class",)
    search_fields = ("user__phone", "user__first_name", "user__last_name", "live_class__title")
    autocomplete_fields = ("user", "live_class")
    raw_id_fields = ("order",)
