from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Category, Chapter, Course, Enrollment, Lesson, LessonFile


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("title", "order", "course_count")
    list_editable = ("order",)
    search_fields = ("title",)
    prepopulated_fields = {"slug": ("title",)}

    @admin.display(description="تعداد دوره")
    def course_count(self, obj):
        return obj.courses.count()


class ChapterInline(admin.TabularInline):
    model = Chapter
    extra = 0
    fields = ("title", "order", "lessons_link")
    readonly_fields = ("lessons_link",)

    @admin.display(description="جلسه‌ها")
    def lessons_link(self, obj):
        if not obj.pk:
            return "—"
        url = reverse("admin:catalog_chapter_change", args=[obj.pk])
        return format_html('<a href="{}">مدیریت جلسه‌ها ({})</a>', url, obj.lessons.count())


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "level", "price", "access_days", "is_published", "order")
    list_editable = ("is_published", "order")
    list_filter = ("is_published", "category", "level")
    search_fields = ("title", "summary")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("prerequisites",)
    inlines = [ChapterInline]
    fieldsets = (
        (None, {"fields": ("title", "slug", "category", "level", "summary", "description")}),
        ("تصویر و ترتیب", {"fields": ("cover", "order", "is_published")}),
        ("فروش و دسترسی", {"fields": ("price", "access_days", "prerequisites")}),
    )
    actions = ["publish", "unpublish"]

    @admin.action(description="انتشار دوره‌های انتخاب‌شده")
    def publish(self, request, queryset):
        queryset.update(is_published=True)

    @admin.action(description="لغو انتشار دوره‌های انتخاب‌شده")
    def unpublish(self, request, queryset):
        queryset.update(is_published=False)


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0
    fields = ("title", "kind", "duration_minutes", "is_free", "is_published", "order", "edit")
    readonly_fields = ("edit",)

    @admin.display(description="جزئیات و فایل‌ها")
    def edit(self, obj):
        if not obj.pk:
            return "—"
        url = reverse("admin:catalog_lesson_change", args=[obj.pk])
        return format_html('<a href="{}">ویرایش ({} فایل)</a>', url, obj.files.count())


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "order")
    list_filter = ("course",)
    search_fields = ("title", "course__title")
    inlines = [LessonInline]


class LessonFileInline(admin.TabularInline):
    model = LessonFile
    extra = 1
    fields = ("title", "file", "order")


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "chapter", "kind", "is_free", "is_published", "order")
    list_filter = ("kind", "is_free", "is_published", "chapter__course")
    search_fields = ("title", "chapter__title", "chapter__course__title")
    list_select_related = ("chapter", "chapter__course")
    autocomplete_fields = ("chapter",)
    inlines = [LessonFileInline]
    fields = (
        "chapter",
        "title",
        "kind",
        "body",
        "duration_minutes",
        "is_free",
        "is_published",
        "order",
    )


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "starts_at", "expires_at", "active", "source")
    list_filter = ("source", "course")
    search_fields = ("user__phone", "user__first_name", "user__last_name", "course__title")
    autocomplete_fields = ("user", "course")
    list_select_related = ("user", "course")
    fields = ("user", "course", "starts_at", "expires_at", "source", "note")

    @admin.display(description="فعال", boolean=True)
    def active(self, obj):
        return obj.is_active
