import io
import shutil
from pathlib import Path

import pytest
from django.core.management import call_command
from django.urls import reverse
from openpyxl import Workbook

from apps.accounts.models import User
from apps.catalog.importer import CoverSource, import_workbook
from apps.catalog.importer_template import build_template
from apps.catalog.models import Category, Course, Lesson
from apps.shop.models import Bundle

SEED = Path(__file__).parent / "seed_data"
CATALOG = SEED / "geoai_catalog.xlsx"


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    yield
    shutil.rmtree(tmp_path, ignore_errors=True)


def _workbook(**sheets):
    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


COURSE_HEADER = ["کد", "عنوان دوره", "دسته", "نوع", "سطح", "قیمت (تومان)", "وضعیت"]


@pytest.mark.django_db
def test_import_geoai_catalog_with_covers():
    covers = CoverSource.from_dir(SEED / "covers")
    with CATALOG.open("rb") as handle:
        report = import_workbook(handle, covers=covers)
    assert report.ok, report.errors
    assert Category.objects.count() == 7
    assert Course.objects.count() == 16
    assert Lesson.objects.count() == 44
    assert Bundle.objects.count() == 4
    assert report.created["تصویر"] == 20

    f2 = Course.objects.get(code="F2")
    assert f2.is_published and f2.price == 0 and f2.access_days is None
    assert f2.slug == "f2-python-for-geospatial" and f2.cover and f2.summary
    assert f2.chapters.count() == 6
    assert all(lesson.is_free for lesson in Lesson.objects.filter(chapter__course=f2))
    video_lesson = Lesson.objects.get(chapter__course=f2, code="L11")
    assert "F2-CH3-L11.mp4" in video_lesson.internal_note and video_lesson.body
    assert video_lesson.kind == Lesson.Kind.VIDEO

    f1 = Course.objects.get(code="F1")
    assert [c.title for c in f1.chapters.all()][0] == "آشنایی با GeoAI و نقشه راه"
    assert Lesson.objects.filter(chapter__course=f1).first().kind == Lesson.Kind.DOCUMENT

    p2 = Course.objects.get(code="P2")
    assert p2.price == 2_250_000 and p2.access_days == 365 and not p2.is_published
    assert set(Course.objects.get(code="P4").prerequisites.values_list("code", flat=True)) == {
        "P2",
        "P3",
    }
    assert Course.objects.get(code="P5").price == 3_300_000

    b1 = Bundle.objects.get(slug="b1-analyst-path")
    assert b1.price == 5_780_000 and b1.courses.count() == 4
    assert b1.access_days == 36500 and not b1.is_published and b1.cover


@pytest.mark.django_db
def test_import_is_idempotent_and_keeps_manual_edits():
    covers = CoverSource.from_dir(SEED / "covers")
    for _ in range(2):
        with CATALOG.open("rb") as handle:
            report = import_workbook(handle, covers=covers)
        assert report.ok
    assert (Course.objects.count(), Lesson.objects.count(), Bundle.objects.count()) == (16, 44, 4)
    assert report.created["تصویر"] == 0 and report.updated["جلسه"] == 44

    lesson = Lesson.objects.get(chapter__course__code="F3", code="L05")
    lesson.title = "عنوان ویرایش‌شده"
    lesson.save()
    with CATALOG.open("rb") as handle:
        import_workbook(handle)
    lesson.refresh_from_db()
    assert lesson.title != "عنوان ویرایش‌شده"
    assert Lesson.objects.filter(chapter__course__code="F3").count() == 18


@pytest.mark.django_db
def test_dry_run_saves_nothing():
    with CATALOG.open("rb") as handle:
        report = import_workbook(handle, covers=CoverSource.from_dir(SEED / "covers"), dry_run=True)
    assert report.ok and report.created["دوره"] == 16
    assert Course.objects.count() == 0 and Lesson.objects.count() == 0


@pytest.mark.django_db
def test_invalid_file_changes_nothing_and_reports_rows():
    buffer = _workbook(
        **{
            "دوره‌ها": [
                COURSE_HEADER,
                ["A1", "دوره خوب", "C1", "رایگان", "مقدماتی", 0, "منتشر"],
                ["A2", "دوره بد", "C1", "پولی", "سطح عجیب", 1000, "منتشر"],
            ]
        }
    )
    report = import_workbook(buffer)
    assert not report.ok
    assert any("ردیف 3" in e and "سطح" in e for e in report.errors)
    assert Course.objects.count() == 0


@pytest.mark.django_db
def test_not_an_excel_file():
    report = import_workbook(io.BytesIO(b"not an excel file"))
    assert not report.ok


@pytest.mark.django_db
def test_lessons_for_unknown_course_is_an_error():
    buffer = _workbook(
        **{
            "درس‌های ZZ9": [
                ["شماره فصل", "فصل", "کد درس", "عنوان درس"],
                [1, "فصل اول", "L01", "جلسه"],
            ]
        }
    )
    report = import_workbook(buffer)
    assert not report.ok and "ZZ9" in report.errors[0]


@pytest.mark.django_db
def test_template_workbook_imports_and_applies_rules():
    report = import_workbook(io.BytesIO(build_template()))
    assert report.ok, report.errors
    s1, s2 = Course.objects.get(code="S1"), Course.objects.get(code="S2")
    assert s1.is_published and not s2.is_published
    assert list(s2.prerequisites.values_list("code", flat=True)) == ["S1"]
    assert Lesson.objects.get(code="L01").is_free  # explicit «بله»
    assert Lesson.objects.get(code="L02").is_free  # course rule «همه»
    bundle = Bundle.objects.get(title="نمونه: مسیر شروع")
    assert bundle.price == 1_050_000 and not bundle.is_published  # (0 + 1.5M) * 0.7, S2 is draft


@pytest.mark.django_db
def test_free_rules_first_n_and_chapter():
    buffer = _workbook(
        **{
            "دوره‌ها": [
                [*COURSE_HEADER, "درس رایگان"],
                ["A1", "یک", "C1", "پولی", "متوسط", 1000, "منتشر", "۲ درس"],
                ["A2", "دو", "C1", "پولی", "متوسط", 1000, "منتشر", "فصل ۲"],
            ],
            "درس‌ها": [
                ["دوره", "شماره فصل", "فصل", "کد درس", "عنوان درس"],
                *[["A1", 1 + i // 2, f"ف{1 + i // 2}", f"L0{i}", f"جلسه {i}"] for i in range(4)],
                *[["A2", 1 + i // 2, f"ف{1 + i // 2}", f"L0{i}", f"جلسه {i}"] for i in range(4)],
            ],
        }
    )
    report = import_workbook(buffer)
    assert report.ok, report.errors

    def flags(code):
        lessons = Lesson.objects.filter(chapter__course__code=code)
        return list(lessons.order_by("chapter__order", "order").values_list("is_free", flat=True))

    a1, a2 = flags("A1"), flags("A2")
    assert a1 == [True, True, False, False]
    assert a2 == [False, False, True, True]


@pytest.mark.django_db
def test_management_command(capsys):
    call_command("import_catalog", str(CATALOG), "--covers", str(SEED / "covers"), "--dry-run")
    assert "بررسی" in capsys.readouterr().out
    assert Course.objects.count() == 0
    call_command("import_catalog", str(CATALOG), "--covers", str(SEED / "covers"))
    assert Course.objects.count() == 16


@pytest.fixture
def staff(db):
    return User.objects.create_user(
        phone="09120000001", password="x", is_staff=True, is_superuser=True
    )


@pytest.mark.django_db
def test_admin_import_page(client, staff):
    client.force_login(staff)
    url = reverse("admin:catalog_course_import")
    assert client.get(url).status_code == 200
    assert client.get(reverse("admin:catalog_course_changelist")).status_code == 200
    template = client.get(reverse("admin:catalog_course_template"))
    assert template["Content-Type"].endswith("spreadsheetml.sheet")

    with CATALOG.open("rb") as handle:
        check = client.post(url, {"workbook": handle, "action": "check"})
    assert check.status_code == 200 and Course.objects.count() == 0
    assert "نتیجه بررسی" in check.content.decode()

    with CATALOG.open("rb") as handle:
        done = client.post(url, {"workbook": handle, "action": "import"})
    assert "ایمپورت با موفقیت انجام شد" in done.content.decode()
    assert Course.objects.count() == 16


@pytest.mark.django_db
def test_admin_import_requires_staff(client, db):
    user = User.objects.create_user(phone="09120000002", password="x")
    client.force_login(user)
    assert client.get(reverse("admin:catalog_course_import")).status_code in (302, 403)
