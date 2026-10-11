import zipfile

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
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


class CatalogImportForm(forms.Form):
    workbook = forms.FileField(label="فایل اکسل (xlsx)")
    covers_zip = forms.FileField(
        label="تصویرها (zip) — اختیاری",
        required=False,
        help_text="تصویر هر دوره/پکیج با نام کد آن (مثلاً F2.png) یا نام ستون «تصویر».",
    )
    replace_covers = forms.BooleanField(
        label="تصویر دوره‌هایی که از قبل تصویر دارند هم جایگزین شود", required=False
    )

    def clean_workbook(self):
        f = self.cleaned_data["workbook"]
        if not f.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("فقط فایل xlsx پذیرفته می‌شود.")
        if f.size > 10 * 1024 * 1024:
            raise forms.ValidationError("حجم فایل اکسل نباید بیشتر از ۱۰ مگابایت باشد.")
        return f

    def clean_covers_zip(self):
        f = self.cleaned_data.get("covers_zip")
        if f:
            if not f.name.lower().endswith(".zip"):
                raise forms.ValidationError("فقط فایل zip پذیرفته می‌شود.")
            if f.size > 100 * 1024 * 1024:
                raise forms.ValidationError("حجم فایل zip نباید بیشتر از ۱۰۰ مگابایت باشد.")
        return f


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    change_list_template = "admin/catalog/course/change_list.html"
    list_display = (
        "title",
        "code",
        "category",
        "level",
        "price",
        "access_days",
        "is_published",
        "order",
    )
    list_editable = ("is_published", "order")
    list_filter = ("is_published", "category", "level")
    search_fields = ("title", "code", "summary")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("prerequisites",)
    inlines = [ChapterInline]
    fieldsets = (
        (
            None,
            {"fields": ("title", "code", "slug", "category", "level", "summary", "description")},
        ),
        ("تصویر و ترتیب", {"fields": ("cover", "order", "is_published")}),
        ("فروش و دسترسی", {"fields": ("price", "access_days", "prerequisites")}),
    )
    actions = ["publish", "unpublish"]

    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [
            path("import-excel/", wrap(self.import_excel), name="catalog_course_import"),
            path("import-template/", wrap(self.import_template), name="catalog_course_template"),
            *super().get_urls(),
        ]

    def _check_import_permission(self, request):
        if not (self.has_add_permission(request) and self.has_change_permission(request)):
            raise PermissionDenied

    def import_template(self, request):
        from .importer_template import build_template

        self._check_import_permission(request)
        response = HttpResponse(
            build_template(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="course-import-template.xlsx"'
        return response

    def import_excel(self, request):
        from .importer import CoverSource, import_workbook

        self._check_import_permission(request)
        form = CatalogImportForm(request.POST or None, request.FILES or None)
        report = None
        if request.method == "POST" and form.is_valid():
            covers = None
            if form.cleaned_data["covers_zip"]:
                try:
                    covers = CoverSource.from_zip(form.cleaned_data["covers_zip"])
                except (ValueError, zipfile.BadZipFile) as exc:
                    form.add_error("covers_zip", f"فایل zip خوانده نشد: {exc}")
            if not form.errors:
                report = import_workbook(
                    form.cleaned_data["workbook"],
                    covers=covers,
                    dry_run=request.POST.get("action") != "import",
                    replace_covers=form.cleaned_data["replace_covers"],
                )
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "ایمپورت دوره‌ها از اکسل",
            "form": form,
            "report": report,
        }
        return TemplateResponse(request, "admin/catalog/course/import_excel.html", context)

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
    change_form_template = "admin/catalog/lesson/change_form.html"
    list_display = ("title", "chapter", "kind", "video_status", "is_free", "is_published", "order")
    list_filter = ("kind", "is_free", "is_published", "chapter__course")
    search_fields = ("title", "code", "chapter__title", "chapter__course__title")
    list_select_related = ("chapter", "chapter__course")
    autocomplete_fields = ("chapter",)
    inlines = [LessonFileInline]
    fields = (
        "chapter",
        "title",
        "code",
        "kind",
        "body",
        "internal_note",
        "duration_minutes",
        "is_free",
        "is_published",
        "order",
    )

    @admin.display(description="ویدیو")
    def video_status(self, obj):
        video = getattr(obj, "video", None)
        return video.get_status_display() if video else "—"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("video")

    def get_urls(self):
        from apps.videos import admin_views as v

        wrap = self.admin_site.admin_view
        return [
            path("<int:lesson_id>/video/", wrap(v.upload_page), name="lesson_video_upload"),
            path("<int:lesson_id>/video/start/", wrap(v.upload_start), name="lesson_video_start"),
            path("<int:lesson_id>/video/chunk/", wrap(v.upload_chunk), name="lesson_video_chunk"),
            path(
                "<int:lesson_id>/video/complete/",
                wrap(v.upload_complete),
                name="lesson_video_complete",
            ),
            path(
                "<int:lesson_id>/video/reprocess/",
                wrap(v.reprocess),
                name="lesson_video_reprocess",
            ),
            *super().get_urls(),
        ]


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
