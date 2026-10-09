"""Chunked uploads: the browser sends the video in small pieces so that slow
connections never hit the reverse proxy's request timeout."""

import re
import shutil
import time
import uuid
from pathlib import Path

from django.conf import settings

CHUNK_SIZE = 5 * 1024 * 1024
MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
_UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")
STALE_AFTER_SECONDS = 24 * 60 * 60


class UploadError(Exception):
    pass


def _uploads_root() -> Path:
    return Path(settings.MEDIA_ROOT) / "protected" / "uploads"


def upload_dir(upload_id: str) -> Path:
    if not _UPLOAD_ID.match(upload_id or ""):
        raise UploadError("شناسه آپلود نامعتبر است.")
    return _uploads_root() / upload_id


def start_upload(filename: str, size: int) -> str:
    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise UploadError("فرمت فایل پشتیبانی نمی‌شود (mp4، mov، mkv، webm).")
    if not 0 < size <= MAX_UPLOAD_SIZE:
        raise UploadError("حجم فایل مجاز نیست (حداکثر ۲ گیگابایت).")
    remove_stale_uploads()
    upload_id = uuid.uuid4().hex
    upload_dir(upload_id).mkdir(parents=True)
    return upload_id


def remove_stale_uploads() -> None:
    """Delete chunks of uploads that were abandoned (e.g. the browser tab was closed)."""
    root = _uploads_root()
    if not root.is_dir():
        return
    cutoff = time.time() - STALE_AFTER_SECONDS
    for directory in root.iterdir():
        if directory.is_dir() and directory.stat().st_mtime < cutoff:
            shutil.rmtree(directory, ignore_errors=True)


def save_chunk(upload_id: str, index: int, data) -> None:
    directory = upload_dir(upload_id)
    if not directory.is_dir():
        raise UploadError("آپلود پیدا نشد؛ دوباره شروع کنید.")
    if not 0 <= index <= MAX_UPLOAD_SIZE // CHUNK_SIZE:
        raise UploadError("شماره قطعه نامعتبر است.")
    if data.size > CHUNK_SIZE:
        raise UploadError("حجم قطعه بیش از حد مجاز است.")
    part = directory / f"{index:06d}.part"
    with open(part.with_suffix(".tmp"), "wb") as out:
        for piece in data.chunks():
            out.write(piece)
    part.with_suffix(".tmp").rename(part)


def assemble(upload_id: str, total_chunks: int, expected_size: int, target: Path) -> None:
    """Concatenate chunks into target, verifying count and size, then clean up."""
    directory = upload_dir(upload_id)
    parts = [directory / f"{i:06d}.part" for i in range(total_chunks)]
    try:
        if total_chunks < 1 or not all(p.is_file() for p in parts):
            raise UploadError("بعضی از قطعه‌ها نرسیده‌اند؛ دوباره آپلود کنید.")
        if sum(p.stat().st_size for p in parts) != expected_size:
            raise UploadError("حجم فایل دریافتی با فایل اصلی یکی نیست؛ دوباره آپلود کنید.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as out:
            for part in parts:
                with open(part, "rb") as src:
                    shutil.copyfileobj(src, out, 1024 * 1024)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
