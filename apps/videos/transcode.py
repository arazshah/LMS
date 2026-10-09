"""Convert an uploaded video into adaptive HLS (1080p/720p/480p) with ffmpeg."""

import json
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

SEGMENT_SECONDS = 6
FFMPEG_TIMEOUT = 2 * 60 * 60


@dataclass(frozen=True)
class Rendition:
    height: int
    crf: int
    maxrate: str
    bufsize: str
    audio_bitrate: str


# Quality-based encoding (CRF) keeps mostly-static lecture/screen recordings small;
# maxrate caps peaks so each level stays watchable on slow Iranian connections.
RENDITIONS = [
    Rendition(1080, 23, "4500k", "9000k", "128k"),
    Rendition(720, 23, "2500k", "5000k", "128k"),
    Rendition(480, 24, "1000k", "2000k", "96k"),
]


class TranscodeError(Exception):
    pass


@dataclass
class ProbeResult:
    width: int
    height: int
    duration: float
    has_audio: bool


def probe(path: Path) -> ProbeResult:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams",
             "-show_format", str(path)],
            capture_output=True, text=True, check=True, timeout=120,
        )  # fmt: skip
        data = json.loads(result.stdout)
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        raise TranscodeError("فایل ویدیو قابل خواندن نیست.") from exc

    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise TranscodeError("فایل هیچ تصویر ویدیویی ندارد.")
    has_audio = any(s.get("codec_type") == "audio" for s in data["streams"])
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    return ProbeResult(int(video["width"]), int(video["height"]), duration, has_audio)


def pick_renditions(source_height: int) -> list[Rendition]:
    """Never upscale; always produce at least one rendition."""
    chosen = [r for r in RENDITIONS if r.height <= source_height]
    if not chosen:
        even_height = max(2, source_height - source_height % 2)
        chosen = [replace(RENDITIONS[-1], height=even_height)]
    return chosen


def build_command(source: Path, out_dir: Path, info: ProbeResult) -> list[str]:
    renditions = pick_renditions(info.height)
    n = len(renditions)
    splits = "".join(f"[v{i}]" for i in range(n))
    scales = ";".join(f"[v{i}]scale=-2:{r.height}[v{i}o]" for i, r in enumerate(renditions))
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-filter_complex", f"[0:v]split={n}{splits};{scales}",
    ]  # fmt: skip
    for i, r in enumerate(renditions):
        cmd += [
            "-map", f"[v{i}o]", f"-c:v:{i}", "libx264", f"-crf:v:{i}", str(r.crf),
            f"-maxrate:v:{i}", r.maxrate, f"-bufsize:v:{i}", r.bufsize,
        ]  # fmt: skip
        if info.has_audio:
            cmd += ["-map", "a:0", f"-c:a:{i}", "aac", f"-b:a:{i}", r.audio_bitrate, "-ac", "2"]
    stream_map = " ".join(
        f"v:{i},a:{i},name:{r.height}p" if info.has_audio else f"v:{i},name:{r.height}p"
        for i, r in enumerate(renditions)
    )
    cmd += [
        "-preset", "veryfast", "-profile:v", "main", "-pix_fmt", "yuv420p",
        "-sc_threshold", "0",
        "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_SECONDS})",
        "-f", "hls", "-hls_time", str(SEGMENT_SECONDS), "-hls_playlist_type", "vod",
        "-hls_flags", "independent_segments",
        "-hls_segment_filename", str(out_dir / "%v" / "seg_%05d.ts"),
        "-master_pl_name", "master.m3u8",
        "-var_stream_map", stream_map,
        str(out_dir / "%v" / "index.m3u8"),
    ]  # fmt: skip
    return cmd


def transcode(source: Path, target_dir: Path) -> tuple[ProbeResult, list[Rendition]]:
    """Write HLS output into target_dir (replaced atomically). Raises TranscodeError."""
    info = probe(source)
    work_dir = target_dir.with_name(target_dir.name + ".tmp")
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True)
    try:
        subprocess.run(
            build_command(source, work_dir, info),
            capture_output=True, text=True, check=True, timeout=FFMPEG_TIMEOUT,
        )  # fmt: skip
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise TranscodeError(f"خطای ffmpeg: {exc.stderr[-1500:]}") from exc
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise TranscodeError("تبدیل ویدیو بیش از حد طول کشید.") from exc
    except OSError as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise TranscodeError(f"اجرای ffmpeg ممکن نشد: {exc}") from exc

    shutil.rmtree(target_dir, ignore_errors=True)
    work_dir.rename(target_dir)
    return info, pick_renditions(info.height)
