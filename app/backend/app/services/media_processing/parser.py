"""Deterministic ffprobe JSON → validated metadata.

Stream selection rules
----------------------
Video: prefer the first stream with ``codec_type == "video"`` whose
``disposition.default`` is 1; otherwise the first video stream in order.
Audio: same rule among ``codec_type == "audio"``.
Subtitle count: number of streams with ``codec_type`` in
``{"subtitle", "text"}`` (ffprobe variants).
Unavailable numeric values (missing, empty, ``N/A``, non-numeric) → ``None``.
Rational frame rates (``24000/1001``) are evaluated when both parts are finite
and denominator ≠ 0; otherwise ``None``.
Zero or negative duration is treated as unavailable (``None``) and may surface
as unsupported when neither video nor audio streams exist.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.services.media_processing.errors import ProbeParseError, UnsupportedMediaError


@dataclass(frozen=True)
class ProbeMetadata:
    container_format: str | None
    duration_seconds: float | None
    overall_bitrate: int | None
    video_codec: str | None
    video_profile: str | None
    video_width: int | None
    video_height: int | None
    display_aspect_ratio: str | None
    video_frame_rate: float | None
    video_bitrate: int | None
    pixel_format: str | None
    audio_codec: str | None
    audio_channels: int | None
    audio_channel_layout: str | None
    audio_sample_rate: int | None
    audio_bitrate: int | None
    audio_stream_count: int
    subtitle_stream_count: int
    filtered_probe: dict[str, Any]
    probe_version: str | None

    def as_filter_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_na(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip().upper() in {"", "N/A", "NA"}:
        return True
    return False


def parse_rational(value: Any) -> float | None:
    if _is_na(value):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number > 0 else None
    text = str(value).strip()
    if "/" in text:
        left, _, right = text.partition("/")
        try:
            num = float(left)
            den = float(right)
        except ValueError:
            return None
        if den == 0:
            return None
        result = num / den
        return result if result > 0 else None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if number > 0 else None


def parse_int(value: Any) -> int | None:
    if _is_na(value):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def parse_float(value: Any) -> float | None:
    if _is_na(value):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number


def _stream_default_rank(stream: dict[str, Any]) -> tuple[int, int]:
    disposition = stream.get("disposition") or {}
    default = 1 if int(disposition.get("default") or 0) == 1 else 0
    index = parse_int(stream.get("index")) or 10_000
    return (-default, index)


def select_stream(streams: list[dict[str, Any]], codec_type: str) -> dict[str, Any] | None:
    matches = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == codec_type]
    if not matches:
        return None
    return sorted(matches, key=_stream_default_rank)[0]


def filter_probe_json(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep a bounded, non-secret subset of ffprobe output for diagnostics."""
    raw_format = raw.get("format")
    fmt: dict[str, Any] = raw_format if isinstance(raw_format, dict) else {}
    raw_streams = raw.get("streams")
    streams_in: list[Any] = raw_streams if isinstance(raw_streams, list) else []
    streams_out: list[dict[str, Any]] = []
    for stream in streams_in[:32]:
        if not isinstance(stream, dict):
            continue
        streams_out.append(
            {
                "index": stream.get("index"),
                "codec_name": stream.get("codec_name"),
                "codec_type": stream.get("codec_type"),
                "profile": stream.get("profile"),
                "width": stream.get("width"),
                "height": stream.get("height"),
                "pix_fmt": stream.get("pix_fmt"),
                "avg_frame_rate": stream.get("avg_frame_rate"),
                "r_frame_rate": stream.get("r_frame_rate"),
                "bit_rate": stream.get("bit_rate"),
                "channels": stream.get("channels"),
                "channel_layout": stream.get("channel_layout"),
                "sample_rate": stream.get("sample_rate"),
                "duration": stream.get("duration"),
                "disposition": {
                    "default": (stream.get("disposition") or {}).get("default"),
                }
                if isinstance(stream.get("disposition"), dict)
                else None,
            }
        )
    return {
        "format": {
            "format_name": fmt.get("format_name"),
            "format_long_name": fmt.get("format_long_name"),
            "duration": fmt.get("duration"),
            "size": fmt.get("size"),
            "bit_rate": fmt.get("bit_rate"),
            "nb_streams": fmt.get("nb_streams"),
        },
        "streams": streams_out,
    }


def parse_ffprobe_payload(
    raw: dict[str, Any], *, probe_version: str | None = None
) -> ProbeMetadata:
    if not isinstance(raw, dict):
        raise ProbeParseError("ffprobe payload must be an object")
    streams_raw = raw.get("streams")
    if streams_raw is None:
        streams: list[dict[str, Any]] = []
    elif not isinstance(streams_raw, list):
        raise ProbeParseError("ffprobe streams must be a list")
    else:
        streams = [s for s in streams_raw if isinstance(s, dict)]

    raw_format = raw.get("format")
    fmt: dict[str, Any] = raw_format if isinstance(raw_format, dict) else {}
    video = select_stream(streams, "video")
    audio = select_stream(streams, "audio")
    audio_count = sum(1 for s in streams if s.get("codec_type") == "audio")
    subtitle_count = sum(1 for s in streams if s.get("codec_type") in {"subtitle", "text"})

    if video is None and audio is None:
        raise UnsupportedMediaError("No video or audio streams detected")

    duration = parse_float(fmt.get("duration"))
    if duration is not None and duration <= 0:
        duration = None

    frame_rate = None
    if video is not None:
        frame_rate = parse_rational(video.get("avg_frame_rate")) or parse_rational(
            video.get("r_frame_rate")
        )

    return ProbeMetadata(
        container_format=(str(fmt["format_name"]) if not _is_na(fmt.get("format_name")) else None),
        duration_seconds=duration,
        overall_bitrate=parse_int(fmt.get("bit_rate")),
        video_codec=(
            str(video["codec_name"]) if video and not _is_na(video.get("codec_name")) else None
        ),
        video_profile=(
            str(video["profile"]) if video and not _is_na(video.get("profile")) else None
        ),
        video_width=parse_int(video.get("width")) if video else None,
        video_height=parse_int(video.get("height")) if video else None,
        display_aspect_ratio=(
            str(video["display_aspect_ratio"])
            if video and not _is_na(video.get("display_aspect_ratio"))
            else None
        ),
        video_frame_rate=frame_rate,
        video_bitrate=parse_int(video.get("bit_rate")) if video else None,
        pixel_format=(
            str(video["pix_fmt"]) if video and not _is_na(video.get("pix_fmt")) else None
        ),
        audio_codec=(
            str(audio["codec_name"]) if audio and not _is_na(audio.get("codec_name")) else None
        ),
        audio_channels=parse_int(audio.get("channels")) if audio else None,
        audio_channel_layout=(
            str(audio["channel_layout"])
            if audio and not _is_na(audio.get("channel_layout"))
            else None
        ),
        audio_sample_rate=parse_int(audio.get("sample_rate")) if audio else None,
        audio_bitrate=parse_int(audio.get("bit_rate")) if audio else None,
        audio_stream_count=audio_count,
        subtitle_stream_count=subtitle_count,
        filtered_probe=filter_probe_json(raw),
        probe_version=probe_version,
    )
