"""
Populate the database with realistic demo data for manual testing.

Run:  python manage.py seed_demo
Re-run: idempotent — skips objects that already exist (matched by title/code).
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()


def _ffmpeg_short_video(path: Path, width: int = 1280, height: int = 720, seconds: int = 6):
    """Generate a short colour-bar test video via ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=440",
        "-t", str(seconds),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
        "-c:a", "aac", "-shortest",
        str(path),
    ]
    subprocess.run(cmd, check=True)


def _ensure_cover(course, color: str = "#1a7a4a"):
    """Create a simple SVG cover image as a PNG placeholder."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (640, 360), color)
        draw = ImageDraw.Draw(img)
        draw.text((60, 150), course.title, fill="white")
        tmp = Path(tempfile.mktemp(suffix=".png"))
        img.save(tmp, "PNG")
        with open(tmp, "rb") as f:
            course.cover.save(f"cover_{course.pk}.png", File(f), save=True)
        tmp.unlink(missing_ok=True)
    except Exception:
        pass  # cover is optional — continue without it


class Command(BaseCommand):
    help = "Create demo categories, courses, lessons, videos, bundles and discount codes"

    def add_arguments(self, parser):
        parser.add_argument(
            "--wipe",
            action="store_true",
            help="Delete ALL existing catalog/shop data first (use only on dev)",
        )

    def handle(self, *args, **options):
        if options["wipe"]:
            from apps.catalog.models import Category
            from apps.live.models import LiveClass
            from apps.shop.models import Bundle, DiscountCode
            Category.objects.all().delete()
            Bundle.objects.all().delete()
            DiscountCode.objects.all().delete()
            LiveClass.objects.all().delete()
            self.stdout.write(self.style.WARNING("Wiped existing data."))

        self._seed()
        self.stdout.write(self.style.SUCCESS("Demo data ready. ادمین می‌تواند خرید را تست کند."))

    # ------------------------------------------------------------------
    def _seed(self):
        from apps.catalog.models import Category, Course, Lesson
        from apps.live.models import LiveClass, LiveSession
        from apps.shop.models import Bundle, DiscountCode

        # ── categories ────────────────────────────────────────────────
        cat_geo, _ = Category.objects.get_or_create(
            title="هوش مصنوعی مکانی",
            defaults={"slug": "geo-ai"},
        )
        cat_rs, _ = Category.objects.get_or_create(
            title="سنجش از دور",
            defaults={"slug": "remote-sensing"},
        )

        # ── course 1: beginner ────────────────────────────────────────
        c1, c1_new = Course.objects.get_or_create(
            title="مقدمه‌ای بر هوش مصنوعی مکانی",
            defaults={
                "category": cat_geo,
                "slug": "intro-geo-ai",
                "level": Course.Level.BEGINNER,
                "price": 0,
                "summary": "در این دوره رایگان با مفاهیم پایه GeoAI آشنا می‌شوید.",
                "description": (
                    "این دوره برای کسانی طراحی شده که تازه وارد دنیای هوش مصنوعی مکانی شده‌اند. "
                    "مفاهیم پایه داده مکانی، شبکه‌های عصبی کانولوشنی "
                    "و ابزارهای متن‌باز را یاد می‌گیرید."
                ),
                "is_published": True,
            },
        )
        if c1_new:
            _ensure_cover(c1, "#1a7a4a")
            self.stdout.write(f"  + دوره: {c1.title}")
        self._add_chapters(c1, [
            ("فصل ۱: آشنایی با داده مکانی", [
                ("داده مکانی چیست؟", Lesson.Kind.TEXT, True),
                ("نصب و راه‌اندازی QGIS", Lesson.Kind.VIDEO, True),
                ("آشنایی با فرمت‌های رایج", Lesson.Kind.DOCUMENT, False),
            ]),
            ("فصل ۲: مقدمات یادگیری ماشین", [
                ("شبکه عصبی کانولوشنی به زبان ساده", Lesson.Kind.VIDEO, False),
                ("نوت‌بوک اول: طبقه‌بندی تصویر", Lesson.Kind.NOTEBOOK, False),
            ]),
        ])

        # ── course 2: intermediate ────────────────────────────────────
        c2, c2_new = Course.objects.get_or_create(
            title="تشخیص ساختمان با یادگیری عمیق",
            defaults={
                "category": cat_geo,
                "slug": "building-detection-dl",
                "level": Course.Level.INTERMEDIATE,
                "price": 1_200_000,
                "access_days": 180,
                "summary": "پیاده‌سازی کامل یک مدل U-Net برای استخراج ساختمان از تصاویر ماهواره‌ای.",
                "description": (
                    "در این دوره از صفر تا نتیجه: آماده‌سازی داده SpaceNet، "
                    "پیاده‌سازی U-Net با PyTorch، "
                    "ارزیابی با IoU و تبدیل خروجی به shapefile."
                ),
                "is_published": True,
            },
        )
        if c2_new:
            _ensure_cover(c2, "#1a5fa0")
            c2.prerequisites.add(c1)
            self.stdout.write(f"  + دوره: {c2.title}")
        self._add_chapters(c2, [
            ("فصل ۱: آماده‌سازی داده", [
                ("دانلود و بررسی داده SpaceNet", Lesson.Kind.VIDEO, True),
                ("تایل‌بندی و آگمنتیشن", Lesson.Kind.NOTEBOOK, False),
                ("داده نمونه برای تمرین", Lesson.Kind.GEODATA, False),
            ]),
            ("فصل ۲: مدل U-Net", [
                ("معماری U-Net — مرور کد", Lesson.Kind.VIDEO, False),
                ("آموزش مدل روی GPU", Lesson.Kind.NOTEBOOK, False),
            ]),
            ("فصل ۳: ارزیابی و صادرات", [
                ("محاسبه IoU و Precision/Recall", Lesson.Kind.VIDEO, False),
                ("صادرات به shapefile با GDAL", Lesson.Kind.CODE, False),
            ]),
        ])

        # ── course 3: advanced ────────────────────────────────────────
        c3, c3_new = Course.objects.get_or_create(
            title="سنجش تغییرات زمین با SAR",
            defaults={
                "category": cat_rs,
                "slug": "sar-change-detection",
                "level": Course.Level.ADVANCED,
                "price": 1_800_000,
                "access_days": 365,
                "summary": "تحلیل تصاویر رادار (Sentinel-1) برای سنجش تغییرات زمین.",
                "description": (
                    "پردازش تصاویر SAR با SNAP و پایتون، تکنیک‌های تشخیص تغییر، "
                    "و کاربرد در پایش سیل، زمین‌لغزش و تغییرات کشاورزی."
                ),
                "is_published": True,
            },
        )
        if c3_new:
            _ensure_cover(c3, "#7a1a1a")
            c3.prerequisites.add(c2)
            self.stdout.write(f"  + دوره: {c3.title}")
        self._add_chapters(c3, [
            ("فصل ۱: مقدمات SAR", [
                ("رادار و تصویر SAR", Lesson.Kind.VIDEO, True),
                ("پیش‌پردازش با SNAP", Lesson.Kind.VIDEO, False),
            ]),
            ("فصل ۲: تشخیص تغییر", [
                ("روش‌های کلاسیک: تفاضل و نسبت", Lesson.Kind.NOTEBOOK, False),
                ("یادگیری عمیق برای SAR", Lesson.Kind.VIDEO, False),
                ("اسکریپت کامل پردازش", Lesson.Kind.CODE, False),
            ]),
        ])

        # ── bundle ────────────────────────────────────────────────────
        bundle, b_new = Bundle.objects.get_or_create(
            title="پکیج کامل GeoAI",
            defaults={
                "slug": "geo-ai-bundle",
                "price": 2_500_000,
                "summary": "سه دوره کامل GeoAI با تخفیف ۳۰٪ نسبت به خرید جداگانه",
                "is_published": True,
            },
        )
        if b_new:
            bundle.courses.set([c1, c2, c3])
            _ensure_cover(bundle, "#4a1a7a")
            self.stdout.write(f"  + پکیج: {bundle.title}")

        # ── discount codes ────────────────────────────────────────────
        codes = [
            dict(code="TEST50", kind=DiscountCode.Kind.PERCENT, value=50,
                 max_discount=500_000, description="۵۰٪ تخفیف آزمایشی"),
            dict(code="FREE100", kind=DiscountCode.Kind.PERCENT, value=100,
                 description="رایگان — برای تست پرداخت صفر"),
            dict(code="GEO200", kind=DiscountCode.Kind.FIXED, value=200_000,
                 min_amount=500_000, description="۲۰۰ هزار تومان تخفیف"),
        ]
        for kw in codes:
            desc = kw.pop("description")
            obj, created = DiscountCode.objects.get_or_create(code=kw["code"], defaults=kw)
            if created:
                self.stdout.write(f"  + کد تخفیف: {obj.code}  ({desc})")

        # ── live class ────────────────────────────────────────────────
        lc, lc_new = LiveClass.objects.get_or_create(
            title="کارگاه زنده: Segment Anything روی تصاویر ماهواره‌ای",
            defaults={
                "slug": "segment-anything-live",
                "price": 800_000,
                "capacity": 20,
                "summary": "کارگاه عملی ۳ جلسه‌ای با Google Meet",
                "is_published": True,
            },
        )
        if lc_new:
            now = timezone.now()
            sessions_data = [
                ("جلسه ۱: آشنایی با SAM", now + timezone.timedelta(days=7)),
                ("جلسه ۲: فاین‌تیون روی داده مکانی", now + timezone.timedelta(days=14)),
                ("جلسه ۳: استقرار و نتایج", now + timezone.timedelta(days=21)),
            ]
            for title, start in sessions_data:
                LiveSession.objects.create(
                    live_class=lc,
                    title=title,
                    starts_at=start.replace(hour=14, minute=0, second=0, microsecond=0),
                    duration_minutes=90,
                    meet_link="https://meet.google.com/demo-test-link",
                    notes="لینک آزمایشی است.",
                )
            self.stdout.write(f"  + کلاس زنده: {lc.title}")

        # ── generate short HLS videos for video lessons ───────────────
        self._ensure_videos()

    # ------------------------------------------------------------------
    def _add_chapters(self, course, chapters_data):
        from apps.catalog.models import Chapter, Lesson

        for order, (chapter_title, lessons_data) in enumerate(chapters_data, 1):
            chapter, _ = Chapter.objects.get_or_create(
                course=course,
                title=chapter_title,
                defaults={"order": order},
            )
            for l_order, (lesson_title, kind, is_free) in enumerate(lessons_data, 1):
                Lesson.objects.get_or_create(
                    chapter=chapter,
                    title=lesson_title,
                    defaults={
                        "kind": kind,
                        "order": l_order,
                        "is_free": is_free,
                        "is_published": True,
                        "body": (
                            f"متن نمونه برای جلسه «{lesson_title}»."
                            "\n\nاین محتوا برای تست سیستم ایجاد شده است."
                        ),
                        "duration_minutes": 8 if kind == Lesson.Kind.VIDEO else 0,
                    },
                )

    def _ensure_videos(self):
        """For every VIDEO lesson without a ready LessonVideo, generate a short HLS."""
        from apps.catalog.models import Lesson
        from apps.videos.models import LessonVideo
        from apps.videos.transcode import transcode

        video_lessons = Lesson.objects.filter(
            kind=Lesson.Kind.VIDEO, is_published=True
        ).exclude(video__status=LessonVideo.Status.READY)

        if not video_lessons.exists():
            return

        if not shutil.which("ffmpeg"):
            self.stdout.write(self.style.WARNING("ffmpeg not found — skipping video generation"))
            return

        self.stdout.write(f"  تولید ویدیو برای {video_lessons.count()} جلسه...")

        for lesson in video_lessons:
            tmp_dir = Path(tempfile.mkdtemp())
            src = tmp_dir / "source.mp4"
            try:
                _ffmpeg_short_video(src, seconds=6)

                video, _ = LessonVideo.objects.get_or_create(lesson=lesson)
                video.status = LessonVideo.Status.PROCESSING
                video.save(update_fields=["status", "updated_at"])

                hls_dir = video.hls_dir
                hls_dir.mkdir(parents=True, exist_ok=True)

                info, renditions = transcode(src, hls_dir)

                video.status = LessonVideo.Status.READY
                video.duration_seconds = round(info.duration)
                video.renditions = "، ".join(f"{r.height}p" for r in renditions)
                video.source = ""
                video.save()

                self.stdout.write(f"    ✓ {lesson.title} ({video.renditions})")
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"    ✗ {lesson.title}: {exc}"))
                if LessonVideo.objects.filter(lesson=lesson).exists():
                    LessonVideo.objects.filter(lesson=lesson).update(
                        status=LessonVideo.Status.FAILED,
                        error=str(exc)[:500],
                    )
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
