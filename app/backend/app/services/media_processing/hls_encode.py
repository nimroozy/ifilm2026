"""HLS VOD encoding via FFmpeg (H.264 + AAC, multi-rendition, local only)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.models.media_encoding import MediaEncodingProfile
from app.services.media_processing.errors import (
    EncodeCancelledError,
    EncodeFailedError,
    PermanentProcessingError,
)
from app.services.media_processing.ffmpeg import resolve_binary, run_process_with_progress
from app.services.media_processing.playlists import VariantRef, write_master_playlist
from app.services.media_processing.profiles import even_width_for_height


@dataclass(frozen=True)
class EncodedRendition:
    profile: MediaEncodingProfile
    label: str
    height: int
    width: int
    bandwidth: int
    playlist_rel: str
    segment_pattern: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def gop_size(*, frame_rate: float | None, segment_seconds: int) -> int:
    fps = float(frame_rate) if frame_rate and frame_rate > 0 else 30.0
    return max(1, int(round(fps * float(segment_seconds))))


def build_hls_rendition_argv(
    *,
    ffmpeg_binary: str,
    source: Path,
    playlist_path: Path,
    segment_pattern: Path,
    profile: MediaEncodingProfile,
    target_width: int,
    target_height: int,
    segment_seconds: int,
    gop: int,
    preset: str,
    has_audio: bool,
) -> list[str]:
    """Build argv for one HLS VOD rendition. Never uses shell."""
    playlist_path.parent.mkdir(parents=True, exist_ok=True)
    argv: list[str] = [
        ffmpeg_binary,
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
    ]
    if has_audio:
        argv.extend(["-map", "0:a:0"])
    argv.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-profile:v",
            profile.video_profile or "main",
            "-pix_fmt",
            "yuv420p",
            "-b:v",
            str(int(profile.video_bitrate)),
            "-maxrate",
            str(int(profile.maxrate)),
            "-bufsize",
            str(int(profile.bufsize)),
            "-g",
            str(gop),
            "-keyint_min",
            str(gop),
            "-sc_threshold",
            "0",
            "-force_key_frames",
            f"expr:gte(t,n_forced*{int(segment_seconds)})",
            "-vf",
            f"scale={target_width}:{target_height}",
        ]
    )
    if has_audio:
        argv.extend(
            [
                "-c:a",
                "aac",
                "-b:a",
                str(int(profile.audio_bitrate)),
                "-ac",
                "2",
                "-ar",
                "48000",
            ]
        )
    else:
        argv.append("-an")
    argv.extend(
        [
            "-f",
            "hls",
            "-hls_time",
            str(int(segment_seconds)),
            "-hls_playlist_type",
            "vod",
            "-hls_flags",
            "independent_segments",
            "-hls_segment_filename",
            str(segment_pattern),
            "-progress",
            "pipe:1",
            "-nostats",
            str(playlist_path),
        ]
    )
    return argv


def encode_hls_renditions(
    *,
    settings: Settings,
    source: Path,
    work_dir: Path,
    profiles: list[MediaEncodingProfile],
    source_width: int,
    source_height: int,
    frame_rate: float | None,
    duration_seconds: float | None,
    has_audio: bool,
    cancel_check: Callable[[], bool] | None = None,
    on_rendition_progress: Callable[[int, int, dict[str, str]], None] | None = None,
) -> list[EncodedRendition]:
    if not profiles:
        raise PermanentProcessingError("No encoding profiles selected", code="no_profiles")
    if source_height <= 0 or source_width <= 0:
        raise PermanentProcessingError("Source dimensions missing", code="probe_required")

    binary = resolve_binary(settings.ffmpeg_binary, label="ffmpeg")
    segment_seconds = int(settings.hls_segment_duration_seconds)
    gop = gop_size(frame_rate=frame_rate, segment_seconds=segment_seconds)
    preset = (settings.hls_x264_preset or "veryfast").strip() or "veryfast"
    timeout = float(settings.media_processing_encode_timeout_seconds)
    # Scale timeout gently with duration and rendition count.
    if duration_seconds and duration_seconds > 0:
        timeout = max(timeout, float(duration_seconds) * 20.0 * len(profiles) + 60.0)

    encoded: list[EncodedRendition] = []
    total = len(profiles)
    for index, profile in enumerate(profiles):
        if cancel_check is not None and cancel_check():
            raise EncodeCancelledError("Encode cancelled")
        if int(profile.height) > int(source_height):
            raise PermanentProcessingError(
                f"Refusing to upscale to {profile.height}p from {source_height}p",
                code="upscale_forbidden",
            )
        target_height = min(int(profile.height), int(source_height))
        target_width = even_width_for_height(source_width, source_height, target_height)
        label = profile.label
        rendition_dir = work_dir / label
        rendition_dir.mkdir(parents=True, exist_ok=True)
        playlist_path = rendition_dir / "index.m3u8"
        segment_pattern = rendition_dir / "segment_%03d.ts"
        argv = build_hls_rendition_argv(
            ffmpeg_binary=binary,
            source=source,
            playlist_path=playlist_path,
            segment_pattern=segment_pattern,
            profile=profile,
            target_width=target_width,
            target_height=target_height,
            segment_seconds=segment_seconds,
            gop=gop,
            preset=preset,
            has_audio=has_audio,
        )

        def _progress(snapshot: dict[str, str], *, _i: int = index) -> None:
            if on_rendition_progress is not None:
                on_rendition_progress(_i, total, snapshot)

        result = run_process_with_progress(
            argv,
            timeout_seconds=timeout,
            max_stderr_bytes=settings.media_processing_log_max_bytes,
            cancel_check=cancel_check,
            on_progress=_progress,
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip() or "ffmpeg encode failed"
            raise EncodeFailedError(err[:2000])
        if not playlist_path.is_file():
            raise EncodeFailedError(f"Missing playlist after encode for {label}")

        bandwidth = int(profile.video_bitrate) + (int(profile.audio_bitrate) if has_audio else 0)
        encoded.append(
            EncodedRendition(
                profile=profile,
                label=label,
                height=target_height,
                width=target_width,
                bandwidth=bandwidth,
                playlist_rel=f"{label}/index.m3u8",
                segment_pattern=str(segment_pattern),
            )
        )

    write_master_playlist(
        work_dir / "master.m3u8",
        [
            VariantRef(
                label=item.label,
                bandwidth=item.bandwidth,
                width=item.width,
                height=item.height,
                playlist_rel=item.playlist_rel,
            )
            for item in encoded
        ],
    )
    return encoded
