import re

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from apps.catalog.models import Lesson

_HLS_PATH = re.compile(r"^(master\.m3u8|\d{2,4}p/(index\.m3u8|seg_\d{5}\.ts))$")
_CONTENT_TYPES = {".m3u8": "application/vnd.apple.mpegurl", ".ts": "video/mp2t"}


def hls(request, lesson_id, path):
    """Serve HLS playlists/segments only to users who can view the lesson."""
    if not _HLS_PATH.match(path):
        raise Http404
    lesson = get_object_or_404(
        Lesson.objects.select_related("chapter__course", "video"),
        pk=lesson_id,
        is_published=True,
        chapter__course__is_published=True,
    )
    video = getattr(lesson, "video", None)
    if video is None or not video.is_ready or not lesson.can_view(request.user):
        raise Http404

    file_path = video.hls_dir / path
    if not file_path.is_file():
        raise Http404
    response = FileResponse(open(file_path, "rb"), content_type=_CONTENT_TYPES[file_path.suffix])
    response["Cache-Control"] = "private, max-age=3600"
    return response
