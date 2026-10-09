from django.contrib import admin
from django.db import transaction
from django.urls import reverse
from django.utils.html import format_html

from .models import LessonVideo
from .tasks import transcode_video


@admin.register(LessonVideo)
class LessonVideoAdmin(admin.ModelAdmin):
    list_display = ("lesson", "status", "renditions", "duration_seconds", "updated_at")
    list_filter = ("status",)
    search_fields = ("lesson__title", "original_name")
    list_select_related = ("lesson",)
    readonly_fields = (
        "lesson_link",
        "original_name",
        "size_bytes",
        "status",
        "renditions",
        "duration_seconds",
        "error",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    actions = ["reprocess"]

    def has_add_permission(self, request):
        return False  # videos are added from the lesson page

    @admin.display(description="جلسه")
    def lesson_link(self, obj):
        url = reverse("admin:catalog_lesson_change", args=[obj.lesson_id])
        return format_html('<a href="{}">{}</a>', url, obj.lesson)

    @admin.action(description="تبدیل دوباره (اگر فایل اصلی موجود باشد)")
    def reprocess(self, request, queryset):
        count = 0
        for video in queryset:
            if video.source:
                video.status = LessonVideo.Status.PENDING
                video.save(update_fields=["status", "updated_at"])
                transaction.on_commit(lambda pk=video.pk: transcode_video.delay(pk))
                count += 1
        self.message_user(request, f"{count} ویدیو در صف تبدیل قرار گرفت.")
