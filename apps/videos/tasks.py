import logging
import math
from pathlib import Path

from celery import shared_task

from .models import LessonVideo
from .transcode import TranscodeError, transcode

logger = logging.getLogger(__name__)


@shared_task(acks_late=True, soft_time_limit=3 * 60 * 60)
def transcode_video(video_id: int) -> None:
    video = LessonVideo.objects.select_related("lesson").filter(pk=video_id).first()
    if video is None or not video.source:
        return
    video.status = LessonVideo.Status.PROCESSING
    video.error = ""
    video.save(update_fields=["status", "error", "updated_at"])

    try:
        info, renditions = transcode(Path(video.source.path), video.hls_dir)
    except Exception as exc:
        # Never leave a video stuck in "processing": record every failure.
        if isinstance(exc, TranscodeError):
            logger.warning("Transcode failed for video %s: %s", video_id, exc)
        else:
            logger.exception("Unexpected error transcoding video %s", video_id)
        video.status = LessonVideo.Status.FAILED
        video.error = str(exc) or exc.__class__.__name__
        video.save(update_fields=["status", "error", "updated_at"])
        return

    video.status = LessonVideo.Status.READY
    video.duration_seconds = round(info.duration)
    video.renditions = "، ".join(f"{r.height}p" for r in renditions)
    # The source is no longer needed once HLS exists; free the disk space.
    video.source.delete(save=False)
    video.save()

    lesson = video.lesson
    if not lesson.duration_minutes and info.duration:
        lesson.duration_minutes = max(1, math.ceil(info.duration / 60))
        lesson.save(update_fields=["duration_minutes"])
