import shutil
from datetime import timedelta

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Category, Chapter, Course, Enrollment, Lesson, LessonFile


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    yield
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def course(db):
    category = Category.objects.create(title="هوش مصنوعی مکانی")
    course = Course.objects.create(
        category=category,
        title="تشخیص ساختمان با یادگیری عمیق",
        price=1_500_000,
        access_days=180,
        is_published=True,
    )
    chapter = Chapter.objects.create(course=course, title="مقدمه", order=1)
    Lesson.objects.create(chapter=chapter, title="معرفی دوره", is_free=True, order=1)
    paid = Lesson.objects.create(chapter=chapter, title="داده‌های آموزشی", order=2, body="متن")
    LessonFile.objects.create(
        lesson=paid, title="نوت‌بوک", file=ContentFile(b"notebook-bytes", name="lab.ipynb")
    )
    return course


@pytest.fixture
def student(db):
    return User.objects.create_user("09121111111", first_name="دانشجو")


def _lessons(course):
    free, paid = course.published_lessons()
    return free, paid


def test_slug_is_generated_from_persian_title(course):
    assert course.slug == "تشخیص-ساختمان-با-یادگیری-عمیق"
    other = Course.objects.create(category=course.category, title=course.title)
    assert other.slug == f"{course.slug}-2"


def test_enrollment_expiry_defaults_to_course_access_days(course, student):
    enrollment = Enrollment.objects.create(user=student, course=course)
    assert enrollment.expires_at - enrollment.starts_at == timedelta(days=180)

    course.access_days = None
    course.save()
    unlimited = Enrollment.objects.create(user=student, course=course)
    assert unlimited.expires_at is None


def test_course_list_and_detail_show_only_published(client, course):
    hidden = Course.objects.create(category=course.category, title="پیش‌نویس")
    response = client.get(reverse("catalog:course_list"))
    assert course.title in response.content.decode()
    assert hidden.title not in response.content.decode()
    assert client.get(course.get_absolute_url()).status_code == 200
    assert client.get(hidden.get_absolute_url()).status_code == 404


def test_course_list_category_filter(client, course):
    other = Category.objects.create(title="سنجش از دور")
    Course.objects.create(category=other, title="طبقه‌بندی تصاویر", is_published=True)
    response = client.get(reverse("catalog:course_list"), {"category": other.slug})
    body = response.content.decode()
    assert "طبقه‌بندی تصاویر" in body and course.title not in body


def test_home_lists_published_courses(client, course):
    response = client.get(reverse("core:home"))
    assert course.title in response.content.decode()


def test_free_lesson_is_public(client, course):
    free, _ = _lessons(course)
    response = client.get(free.get_absolute_url())
    assert response.status_code == 200
    assert response.context["can_view"]


def test_paid_lesson_requires_login(client, course):
    _, paid = _lessons(course)
    response = client.get(paid.get_absolute_url())
    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


def test_paid_lesson_locked_without_enrollment(client, course, student):
    _, paid = _lessons(course)
    client.force_login(student)
    response = client.get(paid.get_absolute_url())
    assert response.status_code == 200
    assert not response.context["can_view"]
    assert "متن" not in response.content.decode().split("<article")[1].split("</article>")[0]


def test_enrolled_student_sees_lesson_and_downloads_file(client, course, student):
    _, paid = _lessons(course)
    Enrollment.objects.create(user=student, course=course)
    client.force_login(student)
    assert client.get(paid.get_absolute_url()).context["can_view"]

    item = paid.files.get()
    response = client.get(item.get_absolute_url())
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"notebook-bytes"
    assert "attachment" in response["Content-Disposition"]


def test_expired_enrollment_has_no_access(client, course, student):
    _, paid = _lessons(course)
    Enrollment.objects.create(
        user=student,
        course=course,
        starts_at=timezone.now() - timedelta(days=200),
        expires_at=timezone.now() - timedelta(days=1),
    )
    client.force_login(student)
    assert not client.get(paid.get_absolute_url()).context["can_view"]
    assert client.get(paid.files.get().get_absolute_url()).status_code == 404


def test_file_download_requires_access(client, course, student):
    _, paid = _lessons(course)
    url = paid.files.get().get_absolute_url()
    assert client.get(url).status_code == 302  # anonymous -> login
    client.force_login(student)
    assert client.get(url).status_code == 404


def test_staff_can_view_everything(client, course):
    _, paid = _lessons(course)
    client.force_login(User.objects.create_superuser("09120000001", "pass-12345"))
    assert client.get(paid.get_absolute_url()).context["can_view"]


def test_free_course_is_open_to_everyone(client, course):
    course.price = 0
    course.save()
    _, paid = _lessons(course)
    assert client.get(paid.get_absolute_url()).context["can_view"]


def test_unpublished_lesson_is_hidden(client, course, student):
    _, paid = _lessons(course)
    paid.is_published = False
    paid.save()
    Enrollment.objects.create(user=student, course=course)
    client.force_login(student)
    assert client.get(paid.get_absolute_url()).status_code == 404


def test_lesson_url_must_match_course(client, course):
    free, _ = _lessons(course)
    other = Course.objects.create(category=course.category, title="دیگر", is_published=True)
    url = reverse("catalog:lesson_detail", args=[other.slug, free.pk])
    assert client.get(url).status_code == 404


def test_lesson_navigation(client, course):
    free, paid = _lessons(course)
    response = client.get(free.get_absolute_url())
    assert response.context["prev_lesson"] is None
    assert response.context["next_lesson"] == paid


def test_my_courses_splits_active_and_expired(client, course, student):
    other = Course.objects.create(category=course.category, title="دوره دوم", is_published=True)
    Enrollment.objects.create(user=student, course=course)
    Enrollment.objects.create(
        user=student,
        course=other,
        starts_at=timezone.now() - timedelta(days=10),
        expires_at=timezone.now() - timedelta(days=1),
    )
    client.force_login(student)
    response = client.get(reverse("catalog:my_courses"))
    assert [e.course for e in response.context["active"]] == [course]
    assert [e.course for e in response.context["expired"]] == [other]


def test_my_courses_requires_login(client):
    response = client.get(reverse("catalog:my_courses"))
    assert response.status_code == 302


def test_public_media_served_but_protected_media_not(client, course):
    public = settings.MEDIA_ROOT / "public" / "covers"
    public.mkdir(parents=True)
    (public / "x.png").write_bytes(b"png")
    assert client.get("/media/public/covers/x.png").status_code == 200

    protected_name = course.published_lessons()[1].files.get().file.name
    assert protected_name.startswith("protected/")
    assert client.get(f"/media/{protected_name}").status_code == 404


def test_admin_pages_load(client, course):
    client.force_login(User.objects.create_superuser("09120000001", "pass-12345"))
    lesson = course.published_lessons()[1]
    for url in [
        reverse("admin:catalog_course_change", args=[course.pk]),
        reverse("admin:catalog_chapter_change", args=[lesson.chapter.pk]),
        reverse("admin:catalog_lesson_change", args=[lesson.pk]),
        reverse("admin:catalog_enrollment_add"),
        reverse("admin:catalog_course_changelist"),
    ]:
        assert client.get(url).status_code == 200, url


@pytest.mark.parametrize(
    "path",
    [
        "public/../protected/receipts/r.png",
        "public/covers/../../protected/receipts/r.png",
        "public/./../protected/receipts/r.png",
    ],
)
def test_public_media_cannot_escape_into_protected_files(rf, path):
    from django.http import Http404

    from apps.core.views import public_media

    protected = settings.MEDIA_ROOT / "protected" / "receipts"
    protected.mkdir(parents=True)
    (protected / "r.png").write_bytes(b"SECRET")
    with pytest.raises(Http404):
        public_media(rf.get("/"), path)


def test_public_media_traversal_over_http(client, db):
    protected = settings.MEDIA_ROOT / "protected" / "receipts"
    protected.mkdir(parents=True)
    (protected / "r.png").write_bytes(b"SECRET")
    response = client.get("/media/public/../protected/receipts/r.png")
    assert response.status_code == 404
