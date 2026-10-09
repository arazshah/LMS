from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render

from .models import Category, Chapter, Course, Enrollment, Lesson, LessonFile


def _published_courses():
    return Course.objects.filter(is_published=True).select_related("category")


def course_list(request):
    courses = _published_courses()
    categories = Category.objects.annotate(
        n=Count("courses", filter=Q(courses__is_published=True))
    ).filter(n__gt=0)
    current = None
    if slug := request.GET.get("category"):
        current = get_object_or_404(Category, slug=slug)
        courses = courses.filter(category=current)
    return render(
        request,
        "catalog/course_list.html",
        {"courses": courses, "categories": categories, "current_category": current},
    )


def course_detail(request, slug):
    course = get_object_or_404(_published_courses(), slug=slug)
    lessons = Lesson.objects.filter(is_published=True).prefetch_related("files")
    chapters = course.chapters.prefetch_related(Prefetch("lessons", queryset=lessons))
    enrollment = None
    if request.user.is_authenticated:
        enrollment = Enrollment.objects.active().filter(user=request.user, course=course).first()
    return render(
        request,
        "catalog/course_detail.html",
        {
            "course": course,
            "chapters": chapters,
            "has_access": course.has_access(request.user),
            "enrollment": enrollment,
            "prerequisites": course.prerequisites.filter(is_published=True),
            "bundles": course.bundles.filter(is_published=True),
        },
    )


def lesson_detail(request, course_slug, lesson_id):
    lesson = get_object_or_404(
        Lesson.objects.select_related("chapter__course", "video"),
        pk=lesson_id,
        is_published=True,
        chapter__course__slug=course_slug,
        chapter__course__is_published=True,
    )
    course = lesson.course
    can_view = lesson.can_view(request.user)
    if not can_view and not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())

    lessons = list(course.published_lessons())
    index = next(i for i, item in enumerate(lessons) if item.pk == lesson.pk)
    lesson_qs = Lesson.objects.filter(is_published=True)
    chapters = Chapter.objects.filter(course=course).prefetch_related(
        Prefetch("lessons", queryset=lesson_qs)
    )
    return render(
        request,
        "catalog/lesson_detail.html",
        {
            "course": course,
            "lesson": lesson,
            "can_view": can_view,
            "video": getattr(lesson, "video", None),
            "chapters": chapters,
            "prev_lesson": lessons[index - 1] if index > 0 else None,
            "next_lesson": lessons[index + 1] if index + 1 < len(lessons) else None,
        },
    )


def lesson_file(request, file_id):
    item = get_object_or_404(
        LessonFile.objects.select_related("lesson__chapter__course"),
        pk=file_id,
        lesson__is_published=True,
    )
    if not item.lesson.can_view(request.user):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        raise Http404
    try:
        handle = item.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404 from exc
    return FileResponse(handle, as_attachment=True, filename=item.filename)


@login_required
def my_courses(request):
    enrollments = (
        Enrollment.objects.filter(user=request.user)
        .select_related("course", "course__category")
        .order_by("-expires_at")
    )
    active, expired, seen = [], [], set()
    for enrollment in enrollments:
        if enrollment.course_id in seen:
            continue
        if enrollment.is_active:
            seen.add(enrollment.course_id)
            active.append(enrollment)
    for enrollment in enrollments:
        if enrollment.course_id not in seen:
            seen.add(enrollment.course_id)
            expired.append(enrollment)
    live = [
        r.live_class
        for r in request.user.live_registrations.select_related("live_class").prefetch_related(
            "live_class__sessions"
        )
    ]
    return render(
        request, "catalog/my_courses.html", {"active": active, "expired": expired, "live": live}
    )
