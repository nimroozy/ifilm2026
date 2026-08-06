"""Catalog audio / subtitle availability builders.

Source priority (highest first):
1. package_manifest — packaged EXT-X-MEDIA tracks (deferred until encoder ships them)
2. media_probe — ffprobe stream languages / counts from the active media asset
3. admin_metadata — movies/series audio, subtitles, dubbed JSON arrays
4. tmdb_metadata — original_language only (never invents local dubs/subs)
5. unknown

Important:
- TMDB original_language does NOT prove a local playable original-language track.
- Catalog admin arrays are claims, not package tracks, unless source says otherwise.
- Dubbed = alternate audio language that differs from original AND is marked as a dub.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.services.languages import (
    normalize_language_list,
    resolve_original_language_code,
)

AvailabilitySource = Literal[
    "media_probe",
    "package_manifest",
    "admin_metadata",
    "tmdb_metadata",
    "unknown",
]


class AudioAvailability(BaseModel):
    original_language: str | None = None
    languages: list[str] = Field(default_factory=list)
    dubbed_languages: list[str] = Field(default_factory=list)
    track_count: int | None = None
    source: AvailabilitySource = "unknown"
    selectable_in_player: bool = False


class SubtitleAvailability(BaseModel):
    languages: list[str] = Field(default_factory=list)
    track_count: int | None = None
    source: AvailabilitySource = "unknown"
    selectable_in_player: bool = False


def _probe_track_languages(probe_json: dict[str, Any] | None, codec_types: set[str]) -> list[dict[str, Any]]:
    if not isinstance(probe_json, dict):
        return []
    streams = probe_json.get("streams")
    if not isinstance(streams, list):
        return []
    out: list[dict[str, Any]] = []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        if stream.get("codec_type") not in codec_types:
            continue
        tags = stream.get("tags") if isinstance(stream.get("tags"), dict) else {}
        disposition = stream.get("disposition") if isinstance(stream.get("disposition"), dict) else {}
        assert isinstance(tags, dict)
        assert isinstance(disposition, dict)
        lang = tags.get("language") or tags.get("LANGUAGE")
        out.append(
            {
                "language": lang,
                "title": tags.get("title"),
                "disposition": disposition,
            }
        )
    return out


def _probe_has_language_data(probe_json: dict[str, Any] | None) -> bool:
    """True when probe_json was produced by a version that retains tags.language."""
    if not isinstance(probe_json, dict):
        return False
    streams = probe_json.get("streams")
    if not isinstance(streams, list):
        return False
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        if "tags" in stream:
            return True
    return False


def derive_dubbed_languages(
    *,
    audio_languages: list[str],
    original_language: str | None,
    admin_dubbed: list[str] | None = None,
    probe_dubbed: list[str] | None = None,
) -> list[str]:
    """Languages that are actual dubs of the original.

    A language is dubbed only when:
    - it is an administered/playable audio language (audio list or explicit dubbed mark),
    - it differs from the original language, and
    - it is marked or derived as a dub (admin ``dubbed`` and/or probe disposition.dub).
    """
    marked = normalize_language_list(admin_dubbed) + [
        c for c in normalize_language_list(probe_dubbed) if c not in normalize_language_list(admin_dubbed)
    ]
    marked_set = set(normalize_language_list(admin_dubbed) + normalize_language_list(probe_dubbed))
    if not marked_set:
        return []

    if audio_languages:
        candidates = [c for c in audio_languages if c in marked_set]
    else:
        # Explicit admin dubbed claim without a separate audio list.
        candidates = list(marked_set)

    out: list[str] = []
    seen: set[str] = set()
    for code in candidates:
        if code in seen:
            continue
        if original_language and code == original_language:
            continue
        seen.add(code)
        out.append(code)
    # Preserve admin dubbed order when possible
    ordered = [c for c in marked if c in seen]
    for c in out:
        if c not in ordered:
            ordered.append(c)
    return ordered


def build_audio_availability(
    *,
    language: Any = None,
    spoken_languages: Any = None,
    metadata_source: str | None = None,
    admin_audio: Any = None,
    admin_dubbed: Any = None,
    probe_json: dict[str, Any] | None = None,
    audio_stream_count: int | None = None,
    has_playable_package: bool = False,
    has_external_media: bool = False,
) -> AudioAvailability:
    original, original_source = resolve_original_language_code(
        language=language,
        spoken_languages=spoken_languages,
        metadata_source=metadata_source,
    )
    admin_audio_codes = normalize_language_list(admin_audio)
    admin_dubbed_codes = normalize_language_list(admin_dubbed)

    probe_audio = _probe_track_languages(probe_json, {"audio"})
    probe_langs = normalize_language_list([t.get("language") for t in probe_audio])
    probe_dubbed = normalize_language_list(
        [
            t.get("language")
            for t in probe_audio
            if int((t.get("disposition") or {}).get("dub") or 0) == 1
        ]
    )
    probe_language_ready = _probe_has_language_data(probe_json)

    # Package multi-audio is deferred (encoder maps 0:a:0 only). Never claim
    # package_manifest until EXT-X-MEDIA audio groups exist.
    if probe_language_ready and (probe_langs or audio_stream_count):
        languages = probe_langs
        track_count = audio_stream_count if audio_stream_count is not None else len(probe_audio)
        # If probe has streams but no language tags on those streams, keep count
        if not languages and audio_stream_count:
            track_count = audio_stream_count
        dubbed = derive_dubbed_languages(
            audio_languages=languages or admin_audio_codes,
            original_language=original,
            admin_dubbed=admin_dubbed_codes,
            probe_dubbed=probe_dubbed,
        )
        # Player cannot select multiple packaged tracks yet.
        selectable = False
        return AudioAvailability(
            original_language=original,
            languages=languages,
            dubbed_languages=dubbed,
            track_count=track_count if track_count else None,
            source="media_probe",
            selectable_in_player=selectable,
        )

    if admin_audio_codes or admin_dubbed_codes:
        languages = admin_audio_codes
        dubbed = derive_dubbed_languages(
            audio_languages=languages or admin_dubbed_codes,
            original_language=original,
            admin_dubbed=admin_dubbed_codes,
        )
        return AudioAvailability(
            original_language=original,
            languages=languages,
            dubbed_languages=dubbed,
            track_count=None,  # admin metadata is not a track count
            source="admin_metadata",
            selectable_in_player=False,
        )

    # Counts without languages (legacy probe) — expose count only
    if audio_stream_count is not None and audio_stream_count > 0:
        return AudioAvailability(
            original_language=original,
            languages=[],
            dubbed_languages=[],
            track_count=audio_stream_count,
            source="media_probe",
            selectable_in_player=False,
        )

    # Original language alone (often TMDB) — never invent audio languages/dubs
    if original:
        src: AvailabilitySource
        if original_source == "tmdb_metadata":
            src = "tmdb_metadata"
        elif original_source == "admin_metadata":
            src = "admin_metadata"
        else:
            src = "unknown"
        return AudioAvailability(
            original_language=original,
            languages=[],
            dubbed_languages=[],
            track_count=None,
            source=src,
            selectable_in_player=False,
        )

    _ = has_playable_package, has_external_media
    return AudioAvailability()


def build_subtitle_availability(
    *,
    admin_subtitles: Any = None,
    probe_json: dict[str, Any] | None = None,
    subtitle_stream_count: int | None = None,
) -> SubtitleAvailability:
    admin_codes = normalize_language_list(admin_subtitles)
    probe_subs = _probe_track_languages(probe_json, {"subtitle", "text"})
    probe_langs = normalize_language_list([t.get("language") for t in probe_subs])
    probe_language_ready = _probe_has_language_data(probe_json)

    if probe_language_ready and (probe_langs or subtitle_stream_count):
        languages = probe_langs
        track_count = (
            subtitle_stream_count if subtitle_stream_count is not None else len(probe_subs)
        )
        return SubtitleAvailability(
            languages=languages,
            track_count=track_count if track_count else None,
            source="media_probe",
            # Local packaging does not emit subtitle playlists yet.
            selectable_in_player=False,
        )

    if admin_codes:
        return SubtitleAvailability(
            languages=admin_codes,
            track_count=None,
            source="admin_metadata",
            selectable_in_player=False,
        )

    if subtitle_stream_count is not None and subtitle_stream_count > 0:
        return SubtitleAvailability(
            languages=[],
            track_count=subtitle_stream_count,
            source="media_probe",
            selectable_in_player=False,
        )

    return SubtitleAvailability()


def item_has_dub(audio: AudioAvailability) -> bool:
    return bool(audio.dubbed_languages)


def item_has_subtitles(subs: SubtitleAvailability) -> bool:
    return bool(subs.languages) or (subs.track_count is not None and subs.track_count > 0)


def load_primary_asset_probe(
    db: Session | None, *, movie_id: int | None = None, episode_id: int | None = None
) -> tuple[dict[str, Any] | None, int | None, int | None]:
    """Return (probe_json, audio_stream_count, subtitle_stream_count) for the primary asset."""
    if db is None or (movie_id is None and episode_id is None):
        return None, None, None
    from app.models.media_assets import MediaAsset

    query = db.query(MediaAsset)
    if movie_id is not None:
        query = query.filter(MediaAsset.movie_id == movie_id)
    if episode_id is not None:
        query = query.filter(MediaAsset.episode_id == episode_id)
    # Prefer originals category, then any with probe data
    assets = query.order_by(MediaAsset.id.desc()).limit(20).all()
    if not assets:
        return None, None, None
    preferred = [a for a in assets if (a.category or "") == "originals"] or assets
    asset = preferred[0]
    for candidate in preferred:
        if candidate.probe_json or candidate.audio_stream_count is not None:
            asset = candidate
            break
    return (
        asset.probe_json if isinstance(asset.probe_json, dict) else None,
        asset.audio_stream_count,
        asset.subtitle_stream_count,
    )


def availability_for_movie(
    movie: Any,
    db: Session | None = None,
    *,
    has_playable_package: bool = False,
    has_external_media: bool = False,
) -> tuple[AudioAvailability, SubtitleAvailability]:
    probe_json, audio_count, sub_count = load_primary_asset_probe(db, movie_id=getattr(movie, "id", None))
    audio = build_audio_availability(
        language=getattr(movie, "language", None),
        spoken_languages=getattr(movie, "spoken_languages", None),
        metadata_source=getattr(movie, "metadata_source", None),
        admin_audio=getattr(movie, "audio", None),
        admin_dubbed=getattr(movie, "dubbed", None),
        probe_json=probe_json,
        audio_stream_count=audio_count,
        has_playable_package=has_playable_package,
        has_external_media=has_external_media,
    )
    subs = build_subtitle_availability(
        admin_subtitles=getattr(movie, "subtitles", None),
        probe_json=probe_json,
        subtitle_stream_count=sub_count,
    )
    return audio, subs


def availability_for_series(series: Any, db: Session | None = None) -> tuple[AudioAvailability, SubtitleAvailability]:
    # Series has no directly attached media asset; use admin metadata only.
    _ = db
    audio = build_audio_availability(
        language=getattr(series, "language", None),
        spoken_languages=getattr(series, "spoken_languages", None),
        metadata_source=getattr(series, "metadata_source", None),
        admin_audio=getattr(series, "audio", None),
        admin_dubbed=getattr(series, "dubbed", None),
    )
    subs = build_subtitle_availability(admin_subtitles=getattr(series, "subtitles", None))
    return audio, subs


def availability_for_episode(
    episode: Any, db: Session | None = None, *, series: Any | None = None
) -> tuple[AudioAvailability, SubtitleAvailability]:
    probe_json, audio_count, sub_count = load_primary_asset_probe(
        db, episode_id=getattr(episode, "id", None)
    )
    language = getattr(series, "language", None) if series is not None else None
    spoken = getattr(series, "spoken_languages", None) if series is not None else None
    meta_source = getattr(series, "metadata_source", None) if series is not None else None
    admin_audio = getattr(series, "audio", None) if series is not None else None
    admin_dubbed = getattr(series, "dubbed", None) if series is not None else None
    admin_subs = getattr(series, "subtitles", None) if series is not None else None

    audio = build_audio_availability(
        language=language,
        spoken_languages=spoken,
        metadata_source=meta_source,
        admin_audio=admin_audio,
        admin_dubbed=admin_dubbed,
        probe_json=probe_json,
        audio_stream_count=audio_count,
    )
    subs = build_subtitle_availability(
        admin_subtitles=admin_subs,
        probe_json=probe_json,
        subtitle_stream_count=sub_count,
    )
    return audio, subs
