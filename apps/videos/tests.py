import shutil
import subprocess
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import User
from apps.catalog.models import Category, Chapter, Course, Enrollment, Lesson

from . import uploads
from .models import LessonVideo
from .transcode import build_command, pick_renditions, probe

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def make_video(path: Path, size="640x360", seconds=3, audio=True) -> Path:
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
           "-i", f"testsrc2=size={size}:rate=25"]  # fmt: skip
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440"]
    cmd += ["-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    subprocess.run([*cmd, str(path)], check=True)
    return path


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    return make_video(tmp_path_factory.mktemp("src") / "lecture.mp4")


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def lesson(db):
    category = Category.objects.create(title="GeoAI")
    course = Course.objects.create(
        category=category, title="دوره ویدیویی", price=100_000, is_published=True
    )
    chapter = Chapter.objects.create(course=course, title="فصل")
    return Lesson.objects.create(chapter=chapter, title="جلسه ویدیویی")


@pytest.fixture
def admin_client(client, db):
    client.force_login(User.objects.create_superuser("09120000001", "pass-12345"))
    return client


def upload_via_admin(client, lesson, path: Path, chunk_size=64 * 1024, settings=None):
    """Drive the same start/chunk/complete endpoints the admin page's JS uses."""
    data = path.read_bytes()
    start = client.post(
        reverse("admin:lesson_video_start", args=[lesson.pk]),
        {"filename": path.name, "size": len(data)},
    ).json()
    pieces = [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]
    for index, piece in enumerate(pieces):
        response = client.post(
            reverse("admin:lesson_video_chunk", args=[lesson.pk]),
            {
                "upload_id": start["upload_id"],
                "index": index,
                "chunk": SimpleUploadedFile("blob", piece),
            },
        )
        assert response.status_code == 200, response.content
    return client.post(
        reverse("admin:lesson_video_complete", args=[lesson.pk]),
        {
            "upload_id": start["upload_id"],
            "total_chunks": len(pieces),
            "size": len(data),
            "filename": path.name,
        },
    )


# --- transcoding ------------------------------------------------------------


@pytest.mark.parametrize(
    "height,expected",
    [(1080, [1080, 720, 480]), (720, [720, 480]), (360, [360]), (1440, [1080, 720, 480])],
)
def test_pick_renditions_never_upscales(height, expected):
    assert [r.height for r in pick_renditions(height)] == expected


def test_build_command_without_audio_maps_video_only(tmp_path):
    from .transcode import ProbeResult

    cmd = build_command(tmp_path / "in.mp4", tmp_path, ProbeResult(1280, 720, 10, False))
    assert "a:0" not in cmd
    assert cmd[cmd.index("-var_stream_map") + 1] == "v:0,name:720p v:1,name:480p"


@needs_ffmpeg
def test_probe_reads_video_info(sample_video):
    info = probe(sample_video)
    assert (info.width, info.height, info.has_audio) == (640, 360, True)
    assert 2.5 < info.duration < 3.5


# --- upload + transcode end to end -----------------------------------------


@needs_ffmpeg
@pytest.mark.django_db
def test_chunked_upload_transcodes_to_hls(
    admin_client, lesson, sample_video, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = upload_via_admin(admin_client, lesson, sample_video)
    assert response.status_code == 200, response.content
    assert response.json()["redirect"] == reverse("admin:catalog_lesson_change", args=[lesson.pk])

    video = LessonVideo.objects.get(lesson=lesson)
    assert video.status == LessonVideo.Status.READY, video.error
    assert video.renditions == "360p"
    assert video.duration_seconds == 3
    assert not video.source  # source removed after a successful transcode
    assert (video.hls_dir / "master.m3u8").is_file()
    assert list((video.hls_dir / "360p").glob("seg_*.ts"))
    lesson.refresh_from_db()
    assert lesson.duration_minutes == 1
    assert not any((Path(video.hls_dir).parents[1] / "uploads").glob("*"))


@needs_ffmpeg
@pytest.mark.django_db
def test_video_without_audio_is_supported(
    admin_client, lesson, tmp_path, django_capture_on_commit_callbacks
):
    silent = make_video(tmp_path / "silent.mp4", audio=False, seconds=2)
    with django_capture_on_commit_callbacks(execute=True):
        upload_via_admin(admin_client, lesson, silent)
    assert LessonVideo.objects.get(lesson=lesson).status == LessonVideo.Status.READY


@pytest.mark.django_db
def test_corrupt_video_is_marked_failed(
    admin_client, lesson, tmp_path, django_capture_on_commit_callbacks
):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video" * 1000)
    with django_capture_on_commit_callbacks(execute=True):
        upload_via_admin(admin_client, lesson, broken)
    video = LessonVideo.objects.get(lesson=lesson)
    assert video.status == LessonVideo.Status.FAILED
    assert video.error
    assert video.source  # kept so it can be inspected / re-processed


@needs_ffmpeg
@pytest.mark.django_db
def test_replacing_video_removes_old_files(
    admin_client, lesson, sample_video, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        upload_via_admin(admin_client, lesson, sample_video)
    old_dir = LessonVideo.objects.get(lesson=lesson).hls_dir
    with django_capture_on_commit_callbacks(execute=True):
        upload_via_admin(admin_client, lesson, sample_video)
    new = LessonVideo.objects.get(lesson=lesson)
    assert new.hls_dir != old_dir and not old_dir.exists() and new.hls_dir.exists()

    lesson.delete()
    assert not new.hls_dir.exists()


# --- upload validation ------------------------------------------------------


@pytest.mark.django_db
def test_upload_rejects_bad_extension_and_size(admin_client, lesson):
    url = reverse("admin:lesson_video_start", args=[lesson.pk])
    assert admin_client.post(url, {"filename": "x.exe", "size": 10}).status_code == 400
    too_big = uploads.MAX_UPLOAD_SIZE + 1
    assert admin_client.post(url, {"filename": "x.mp4", "size": too_big}).status_code == 400


@pytest.mark.django_db
def test_upload_detects_missing_chunks_and_size_mismatch(admin_client, lesson):
    start = admin_client.post(
        reverse("admin:lesson_video_start", args=[lesson.pk]), {"filename": "a.mp4", "size": 10}
    ).json()
    admin_client.post(
        reverse("admin:lesson_video_chunk", args=[lesson.pk]),
        {"upload_id": start["upload_id"], "index": 0, "chunk": SimpleUploadedFile("b", b"12345")},
    )
    response = admin_client.post(
        reverse("admin:lesson_video_complete", args=[lesson.pk]),
        {"upload_id": start["upload_id"], "total_chunks": 2, "size": 10, "filename": "a.mp4"},
    )
    assert response.status_code == 400
    assert not LessonVideo.objects.exists()


@pytest.mark.django_db
def test_upload_id_cannot_escape_upload_dir(admin_client, lesson):
    response = admin_client.post(
        reverse("admin:lesson_video_chunk", args=[lesson.pk]),
        {"upload_id": "../../etc", "index": 0, "chunk": SimpleUploadedFile("b", b"x")},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_upload_endpoints_require_staff(client, lesson):
    client.force_login(User.objects.create_user("09121111111"))
    url = reverse("admin:lesson_video_start", args=[lesson.pk])
    response = client.post(url, {"filename": "a.mp4", "size": 10})
    assert response.status_code == 302 and "/login/" in response.url


@pytest.mark.django_db
def test_admin_upload_page_and_lesson_page_load(admin_client, lesson):
    assert (
        admin_client.get(reverse("admin:lesson_video_upload", args=[lesson.pk])).status_code == 200
    )
    response = admin_client.get(reverse("admin:catalog_lesson_change", args=[lesson.pk]))
    assert "آپلود ویدیو" in response.content.decode()


# --- playback access --------------------------------------------------------


def _ready_video(lesson):
    video = LessonVideo.objects.create(lesson=lesson, status=LessonVideo.Status.READY)
    (video.hls_dir / "360p").mkdir(parents=True)
    (video.hls_dir / "master.m3u8").write_text("#EXTM3U\n")
    (video.hls_dir / "360p" / "seg_00000.ts").write_bytes(b"TS")
    return video


def _hls(path, lesson):
    return reverse("videos:hls", args=[lesson.pk, path])


@pytest.mark.django_db
def test_hls_requires_access(client, lesson):
    _ready_video(lesson)
    assert client.get(_hls("master.m3u8", lesson)).status_code == 404

    student = User.objects.create_user("09121111111")
    client.force_login(student)
    assert client.get(_hls("master.m3u8", lesson)).status_code == 404

    Enrollment.objects.create(user=student, course=lesson.course)
    response = client.get(_hls("master.m3u8", lesson))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/vnd.apple.mpegurl"
    segment = client.get(_hls("360p/seg_00000.ts", lesson))
    assert segment["Content-Type"] == "video/mp2t"
    assert b"".join(segment.streaming_content) == b"TS"


@pytest.mark.django_db
def test_hls_free_lesson_is_public(client, lesson):
    _ready_video(lesson)
    lesson.is_free = True
    lesson.save()
    assert client.get(_hls("master.m3u8", lesson)).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["../secret", "360p/../../x.ts", "source.mp4", "360p/evil.sh"])
def test_hls_rejects_unexpected_paths(client, lesson, path):
    _ready_video(lesson)
    lesson.is_free = True
    lesson.save()
    assert client.get(f"/videos/{lesson.pk}/{path}").status_code == 404


@pytest.mark.django_db
def test_hls_not_served_until_ready(client, lesson):
    video = _ready_video(lesson)
    video.status = LessonVideo.Status.PROCESSING
    video.save()
    lesson.is_free = True
    lesson.save()
    assert client.get(_hls("master.m3u8", lesson)).status_code == 404
    response = client.get(lesson.get_absolute_url())
    assert "در حال آماده‌سازی" in response.content.decode()


@pytest.mark.django_db
def test_lesson_page_shows_player_with_watermark(client, lesson):
    _ready_video(lesson)
    student = User.objects.create_user("09121111111")
    Enrollment.objects.create(user=student, course=lesson.course)
    client.force_login(student)
    body = client.get(lesson.get_absolute_url()).content.decode()
    assert "data-hls-player" in body and "09121111111" in body
    assert "dist/hls.min.js" in body


@pytest.mark.django_db
def test_missing_ffmpeg_marks_video_failed(lesson, settings, monkeypatch):
    from . import transcode as transcode_module
    from .tasks import transcode_video

    video = LessonVideo.objects.create(lesson=lesson, source="protected/videos/x/source.mp4")
    path = Path(settings.MEDIA_ROOT) / video.source.name
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x")

    def boom(*args, **kwargs):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(transcode_module.subprocess, "run", boom)
    transcode_video(video.pk)
    video.refresh_from_db()
    assert video.status == LessonVideo.Status.FAILED and video.error
