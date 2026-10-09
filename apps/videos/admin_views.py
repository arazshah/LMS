from pathlib import Path

from django.contrib import admin, messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.catalog.models import Lesson

from . import uploads
from .models import LessonVideo, source_upload_to
from .tasks import transcode_video


def _error(exc):
    return JsonResponse({"error": str(exc)}, status=400)


def upload_page(request, lesson_id):
    lesson = get_object_or_404(Lesson.objects.select_related("chapter__course"), pk=lesson_id)
    context = {
        **admin.site.each_context(request),
        "title": f"آپلود ویدیو: {lesson.title}",
        "lesson": lesson,
        "video": getattr(lesson, "video", None),
        "chunk_size": uploads.CHUNK_SIZE,
        "opts": Lesson._meta,
        "lesson_url": reverse("admin:catalog_lesson_change", args=[lesson.pk]),
    }
    return render(request, "admin/videos/upload.html", context)


@require_POST
def upload_start(request, lesson_id):
    get_object_or_404(Lesson, pk=lesson_id)
    try:
        upload_id = uploads.start_upload(
            request.POST.get("filename", ""), int(request.POST.get("size", 0))
        )
    except (uploads.UploadError, ValueError) as exc:
        return _error(exc)
    return JsonResponse({"upload_id": upload_id, "chunk_size": uploads.CHUNK_SIZE})


@require_POST
def upload_chunk(request, lesson_id):
    chunk = request.FILES.get("chunk")
    if chunk is None:
        return _error("قطعه‌ای دریافت نشد.")
    try:
        uploads.save_chunk(request.POST.get("upload_id", ""), int(request.POST["index"]), chunk)
    except (uploads.UploadError, KeyError, ValueError) as exc:
        return _error(exc)
    return JsonResponse({"ok": True})


@require_POST
def upload_complete(request, lesson_id):
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    filename = Path(request.POST.get("filename", "video.mp4")).name
    if Path(filename).suffix.lower() not in uploads.ALLOWED_EXTENSIONS:
        return _error("فرمت فایل پشتیبانی نمی‌شود.")
    try:
        total = int(request.POST["total_chunks"])
        size = int(request.POST["size"])
    except (KeyError, ValueError) as exc:
        return _error(exc)

    old = LessonVideo.objects.filter(lesson=lesson).first()
    if old is not None:
        old.delete()  # removes old source/HLS files via signal

    video = LessonVideo(lesson=lesson, original_name=filename, size_bytes=size)
    relative = source_upload_to(video, filename)
    try:
        uploads.assemble(
            request.POST.get("upload_id", ""),
            total,
            size,
            Path(video.source.storage.path(relative)),
        )
    except uploads.UploadError as exc:
        return _error(exc)

    video.source.name = relative
    video.save()
    transaction.on_commit(lambda: transcode_video.delay(video.pk))
    messages.success(request, "ویدیو آپلود شد و در صف تبدیل قرار گرفت.")
    return JsonResponse({"redirect": reverse("admin:catalog_lesson_change", args=[lesson.pk])})


@require_POST
def reprocess(request, lesson_id):
    video = get_object_or_404(LessonVideo, lesson_id=lesson_id)
    if not video.source:
        messages.error(request, "فایل اصلی موجود نیست؛ ویدیو را دوباره آپلود کنید.")
    else:
        video.status = LessonVideo.Status.PENDING
        video.save(update_fields=["status", "updated_at"])
        transaction.on_commit(lambda: transcode_video.delay(video.pk))
        messages.success(request, "ویدیو دوباره در صف تبدیل قرار گرفت.")
    return redirect("admin:catalog_lesson_change", lesson_id)
