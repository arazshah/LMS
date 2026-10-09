from django.contrib import admin
from django.utils import timezone

from apps.notify import tasks as notify

from .models import Question


class AnsweredFilter(admin.SimpleListFilter):
    title = "وضعیت پاسخ"
    parameter_name = "answered"

    def lookups(self, request, model_admin):
        return (("no", "بی‌پاسخ"), ("yes", "پاسخ داده شده"))

    def queryset(self, request, queryset):
        if self.value() == "no":
            return queryset.filter(answer="")
        if self.value() == "yes":
            return queryset.exclude(answer="")
        return queryset


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("short_body", "user", "lesson", "course", "answered", "created_at")
    list_filter = (AnsweredFilter, "is_hidden", "lesson__chapter__course")
    search_fields = ("body", "answer", "user__phone", "lesson__title")
    list_select_related = ("user", "lesson__chapter__course")
    readonly_fields = ("user", "lesson", "body", "created_at", "answered_at")
    fields = ("lesson", "user", "created_at", "body", "answer", "answered_at", "is_hidden")

    def has_add_permission(self, request):
        return False

    @admin.display(description="سوال")
    def short_body(self, obj):
        return obj.body[:80]

    @admin.display(description="دوره")
    def course(self, obj):
        return obj.lesson.chapter.course

    @admin.display(description="پاسخ داده شده", boolean=True)
    def answered(self, obj):
        return obj.is_answered

    def save_model(self, request, obj, form, change):
        newly_answered = obj.is_answered and obj.answered_at is None
        if newly_answered:
            obj.answered_at = timezone.now()
        super().save_model(request, obj, form, change)
        if newly_answered:
            notify.question_answered(obj)
