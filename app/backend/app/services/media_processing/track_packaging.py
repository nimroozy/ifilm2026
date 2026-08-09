"""Production multi-audio / subtitle HLS packaging helpers.

Builds alternate audio and WebVTT subtitle renditions plus an EXT-X-MEDIA master.
Falls back to muxed single-audio packaging when no multi-track sources are configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.media_assets import MediaAsset
from app.models.media_tracks import MediaTrack
from app.services.media_processing.errors import PermanentProcessingError
from app.services.media_processing.ffmpeg import resolve_binary, run_process_with_progress
from app.services.media_processing.paths import resolve_completed_asset_path

AUDIO_GROUP = "audio"
SUBS_GROUP = "subs"

# HLS NAME attributes — language-native, not UI-locale strings.
_AUDIO_NAMES: dict[tuple[str, bool], str] = {
    ("en", False): "English",
    ("en", True): "English Dubbed",
    ("fa", False): "فارسی",
    ("fa", True): "فارسی دوبله",
    ("ps", False): "پښتو",
    ("ps", True): "پښتو دوبله",
    ("prs", False): "دری",
    ("prs", True): "دری دوبله",
}
_SUB_NAMES: dict[str, str] = {
    "en": "English",
    "fa": "فارسی",
    "ps": "پښتو",
    "prs": "دری",
}


@dataclass(frozen=True)
class AudioPackPlan:
    track_id: int | None
    source_path: Path
    stream_index: int | None
    label: str
    language: str
    name: str
    is_default: bool
    is_dubbed: bool


@dataclass(frozen=True)
class SubtitlePackPlan:
    track_id: int | None
    source_path: Path
    label: str
    language: str
    name: str


@dataclass(frozen=True)
class PackagingPlan:
    mode: str  # "muxed_single" | "multi_track"
    audio: list[AudioPackPlan]
    subtitles: list[SubtitlePackPlan]
    video_only: bool


def hls_audio_name(*, language_code: str, is_dubbed: bool) -> str:
    key = (language_code, bool(is_dubbed))
    if key in _AUDIO_NAMES:
        return _AUDIO_NAMES[key]
    base = language_code.upper()
    return f"{base} Dubbed" if is_dubbed else base


def hls_subtitle_name(language_code: str) -> str:
    return _SUB_NAMES.get(language_code, language_code.upper())


def audio_rendition_label(language_code: str) -> str:
    return f"audio_{language_code}"[:32]


def subtitle_rendition_label(language_code: str) -> str:
    return f"subs_{language_code}"[:32]


def duration_mismatch(
    *,
    primary_seconds: float | None,
    track_seconds: float | None,
    tolerance_seconds: float,
) -> str | None:
    if primary_seconds is None or track_seconds is None:
        return None
    if primary_seconds <= 0 or track_seconds <= 0:
        return "Audio/subtitle duration missing or invalid"
    delta = abs(float(primary_seconds) - float(track_seconds))
    # Allow small absolute skew or 2% relative (whichever larger), capped by configured floor.
    rel = max(float(tolerance_seconds), float(primary_seconds) * 0.02)
    if delta > rel:
        return (
            f"Track duration {track_seconds:.1f}s differs from primary "
            f"{primary_seconds:.1f}s by {delta:.1f}s (tolerance {rel:.1f}s)"
        )
    return None


def _resolve_source_path(db: Session, track: MediaTrack, primary: MediaAsset) -> Path:
    if track.source_media_asset_id:
        source = db.get(MediaAsset, track.source_media_asset_id)
        if source is None:
            raise PermanentProcessingError(
                f"Track source asset missing for {track.track_type}/{track.language_code}",
                code="track_source_missing",
            )
        if source.upload_status != "completed":
            raise PermanentProcessingError(
                f"Track source asset not completed for {track.language_code}",
                code="track_source_incomplete",
            )
        return resolve_completed_asset_path(source)
    # Embedded stream on the primary asset.
    return resolve_completed_asset_path(primary)


def build_packaging_plan(
    db: Session,
    *,
    primary: MediaAsset,
    settings: Settings,
) -> PackagingPlan:
    tracks = (
        db.query(MediaTrack)
        .filter(MediaTrack.media_asset_id == primary.id)
        .order_by(MediaTrack.sort_order.asc(), MediaTrack.id.asc())
        .all()
    )
    audio_tracks = [t for t in tracks if t.track_type == "audio"]
    sub_tracks = [t for t in tracks if t.track_type == "subtitle"]

    # Multi-track packaging when admin associated sidecars / stream indexes,
    # or when more than one audio/subtitle track is configured.
    needs_multi = bool(sub_tracks) or len(audio_tracks) > 1 or any(
        t.source_media_asset_id or t.source_stream_index is not None for t in audio_tracks
    )
    if not needs_multi:
        return PackagingPlan(mode="muxed_single", audio=[], subtitles=[], video_only=False)

    if not audio_tracks:
        # Subtitles only — demux primary audio as alternate track when present.
        has_primary_audio = bool(primary.audio_stream_count and primary.audio_stream_count > 0)
        audio_plans: list[AudioPackPlan] = []
        if has_primary_audio:
            audio_plans.append(
                AudioPackPlan(
                    track_id=None,
                    source_path=resolve_completed_asset_path(primary),
                    stream_index=0,
                    label=audio_rendition_label("en"),
                    language="en",
                    name=hls_audio_name(language_code="en", is_dubbed=False),
                    is_default=True,
                    is_dubbed=False,
                )
            )
        sub_plans = _build_subtitle_plans(db, primary=primary, tracks=sub_tracks, settings=settings)
        return PackagingPlan(
            mode="multi_track",
            audio=audio_plans,
            subtitles=sub_plans,
            video_only=bool(audio_plans),
        )

    defaults = [t for t in audio_tracks if t.is_default]
    if len(defaults) > 1:
        raise PermanentProcessingError(
            "Only one default audio track is allowed", code="multiple_default_audio"
        )
    default_id = defaults[0].id if defaults else audio_tracks[0].id

    audio_plans = []
    for track in audio_tracks:
        source_path = _resolve_source_path(db, track, primary)
        if track.source_media_asset_id:
            source_asset = db.get(MediaAsset, track.source_media_asset_id)
            assert source_asset is not None
            if not source_asset.audio_stream_count:
                raise PermanentProcessingError(
                    f"Audio source for {track.language_code} has no audio stream",
                    code="track_no_audio",
                )
            mismatch = duration_mismatch(
                primary_seconds=primary.duration_seconds,
                track_seconds=source_asset.duration_seconds,
                tolerance_seconds=float(settings.hls_audio_duration_tolerance_seconds),
            )
            if mismatch:
                raise PermanentProcessingError(mismatch, code="audio_duration_mismatch")
            stream_index = (
                int(track.source_stream_index)
                if track.source_stream_index is not None
                else 0
            )
        else:
            stream_index = (
                int(track.source_stream_index)
                if track.source_stream_index is not None
                else 0
            )
            if not primary.audio_stream_count or stream_index >= int(primary.audio_stream_count):
                raise PermanentProcessingError(
                    f"Primary asset missing audio stream index {stream_index}",
                    code="track_stream_missing",
                )
        lang = track.language_code
        audio_plans.append(
            AudioPackPlan(
                track_id=track.id,
                source_path=source_path,
                stream_index=stream_index,
                label=audio_rendition_label(lang),
                language=lang,
                name=track.hls_name or hls_audio_name(language_code=lang, is_dubbed=track.is_dubbed),
                is_default=track.id == default_id,
                is_dubbed=bool(track.is_dubbed),
            )
        )

    sub_plans = _build_subtitle_plans(db, primary=primary, tracks=sub_tracks, settings=settings)
    return PackagingPlan(
        mode="multi_track",
        audio=audio_plans,
        subtitles=sub_plans,
        video_only=True,
    )


def _build_subtitle_plans(
    db: Session,
    *,
    primary: MediaAsset,
    tracks: list[MediaTrack],
    settings: Settings,
) -> list[SubtitlePackPlan]:
    del settings  # reserved for future encoding knobs
    plans: list[SubtitlePackPlan] = []
    for track in tracks:
        if not track.source_media_asset_id:
            raise PermanentProcessingError(
                f"Subtitle track {track.language_code} requires source_media_asset_id",
                code="subtitle_source_required",
            )
        source = db.get(MediaAsset, track.source_media_asset_id)
        if source is None or source.upload_status != "completed":
            raise PermanentProcessingError(
                f"Subtitle source missing for {track.language_code}",
                code="subtitle_source_missing",
            )
        path = resolve_completed_asset_path(source)
        ext = (source.extension or path.suffix.lstrip(".")).lower()
        if ext not in {"vtt", "srt", "ass", "ssa"}:
            raise PermanentProcessingError(
                f"Unsupported subtitle format .{ext} for {track.language_code}",
                code="subtitle_format_unsupported",
            )
        lang = track.language_code
        plans.append(
            SubtitlePackPlan(
                track_id=track.id,
                source_path=path,
                label=subtitle_rendition_label(lang),
                language=lang,
                name=track.hls_name or hls_subtitle_name(lang),
            )
        )
    return plans


def encode_audio_hls(
    *,
    settings: Settings,
    plan: AudioPackPlan,
    work_dir: Path,
    cancel_check=None,
) -> Path:
    binary = resolve_binary(settings.ffmpeg_binary, label="ffmpeg")
    out_dir = work_dir / plan.label
    out_dir.mkdir(parents=True, exist_ok=True)
    playlist = out_dir / "index.m3u8"
    segment_pattern = out_dir / "segment_%03d.ts"
    argv = [
        binary,
        "-y",
        "-i",
        str(plan.source_path),
        "-vn",
        "-map",
        f"0:a:{plan.stream_index if plan.stream_index is not None else 0}",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-f",
        "hls",
        "-hls_time",
        str(int(settings.hls_segment_duration_seconds)),
        "-hls_playlist_type",
        "vod",
        "-hls_flags",
        "independent_segments",
        "-hls_segment_filename",
        str(segment_pattern),
        "-progress",
        "pipe:1",
        "-nostats",
        str(playlist),
    ]
    result = run_process_with_progress(
        argv,
        timeout_seconds=float(settings.media_processing_encode_timeout_seconds),
        max_stderr_bytes=settings.media_processing_log_max_bytes,
        cancel_check=cancel_check,
    )
    if result.returncode != 0 or not playlist.is_file():
        err = result.stderr.decode("utf-8", errors="replace").strip() or "audio encode failed"
        raise PermanentProcessingError(err[:2000], code="audio_encode_failed")
    return playlist


def package_subtitle_hls(
    *,
    settings: Settings,
    plan: SubtitlePackPlan,
    work_dir: Path,
    cancel_check=None,
) -> Path:
    """Convert subtitle source to WebVTT and wrap as a VOD HLS playlist."""
    binary = resolve_binary(settings.ffmpeg_binary, label="ffmpeg")
    out_dir = work_dir / plan.label
    out_dir.mkdir(parents=True, exist_ok=True)
    vtt_path = out_dir / "subs.vtt"
    argv = [
        binary,
        "-y",
        "-i",
        str(plan.source_path),
        "-map",
        "0:s:0?",
        "-c:s",
        "webvtt",
        str(vtt_path),
    ]
    # For plain .vtt/.srt files ffmpeg may treat them as subtitle inputs without -map.
    if plan.source_path.suffix.lower() in {".vtt", ".srt", ".ass", ".ssa"}:
        argv = [
            binary,
            "-y",
            "-i",
            str(plan.source_path),
            "-c:s",
            "webvtt",
            str(vtt_path),
        ]
    result = run_process_with_progress(
        argv,
        timeout_seconds=min(120.0, float(settings.media_processing_encode_timeout_seconds)),
        max_stderr_bytes=settings.media_processing_log_max_bytes,
        cancel_check=cancel_check,
    )
    if result.returncode != 0 or not vtt_path.is_file():
        # Fallback: if source is already VTT, copy bytes.
        if plan.source_path.suffix.lower() == ".vtt":
            vtt_path.write_bytes(plan.source_path.read_bytes())
        else:
            err = result.stderr.decode("utf-8", errors="replace").strip() or "subtitle convert failed"
            raise PermanentProcessingError(err[:2000], code="subtitle_encode_failed")

    # Ensure WEBVTT header.
    text = vtt_path.read_text(encoding="utf-8", errors="replace")
    if not text.lstrip().upper().startswith("WEBVTT"):
        vtt_path.write_text("WEBVTT\n\n" + text, encoding="utf-8")
        text = vtt_path.read_text(encoding="utf-8")

    # Single-cue-file VOD playlist (compatible with hls.js SUBTITLES group).
    duration = 6.0
    playlist = out_dir / "index.m3u8"
    playlist.write_text(
        (
            "#EXTM3U\n"
            "#EXT-X-VERSION:3\n"
            f"#EXT-X-TARGETDURATION:{int(duration)}\n"
            "#EXT-X-MEDIA-SEQUENCE:0\n"
            "#EXT-X-PLAYLIST-TYPE:VOD\n"
            f"#EXTINF:{duration:.3f},\n"
            "subs.vtt\n"
            "#EXT-X-ENDLIST\n"
        ),
        encoding="utf-8",
    )
    return playlist
