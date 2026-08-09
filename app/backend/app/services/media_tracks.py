"""CRUD helpers for media_tracks + packaging lifecycle hooks."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.media_assets import MediaAsset
from app.models.media_assets import utcnow as asset_utcnow
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage
from app.models.media_tracks import MediaTrack, utcnow
from app.schemas.media_tracks import (
    MediaTrackCreate,
    MediaTrackListOut,
    MediaTrackOut,
    MediaTrackUpdate,
)
from app.services.media_processing.track_packaging import duration_mismatch

ALLOWED_LANG = frozenset({"en", "fa", "ps", "prs", "ar", "hi", "ur", "tr", "ru", "ko", "ja", "zh"})
SUBTITLE_EXTS = frozenset({"vtt", "srt", "ass", "ssa"})


def _normalize_lang(code: str) -> str:
    raw = (code or "").strip().lower().replace("_", "-")
    primary = raw.split("-", 1)[0]
    aliases = {
        "eng": "en",
        "english": "en",
        "fas": "fa",
        "per": "fa",
        "persian": "fa",
        "farsi": "fa",
        "dari": "prs",
        "pus": "ps",
        "pashto": "ps",
        "pushto": "ps",
    }
    return aliases.get(primary, primary)


def list_tracks(db: Session, media_asset_id: str) -> MediaTrackListOut:
    rows = (
        db.query(MediaTrack)
        .filter(MediaTrack.media_asset_id == media_asset_id)
        .order_by(MediaTrack.track_type.asc(), MediaTrack.sort_order.asc(), MediaTrack.id.asc())
        .all()
    )
    items = [MediaTrackOut.model_validate(r) for r in rows]
    return MediaTrackListOut(
        items=items,
        audio=[i for i in items if i.track_type == "audio"],
        subtitles=[i for i in items if i.track_type == "subtitle"],
    )


def _mark_packages_require_repackage(db: Session, media_asset_id: str) -> None:
    """Deactivate active packages so stale masters cannot pretend new tracks exist."""
    now = asset_utcnow()
    packages = (
        db.query(MediaPackage)
        .filter(
            MediaPackage.media_asset_id == media_asset_id,
            MediaPackage.package_type == PACKAGE_TYPE_HLS_VOD,
            MediaPackage.is_active.is_(True),
        )
        .all()
    )
    for package in packages:
        package.is_active = False
        package.superseded_at = now
        package.error_code = "requires_repackage"
        package.error_message = "Track configuration changed; re-run HLS packaging"
        db.add(package)
    asset = db.get(MediaAsset, media_asset_id)
    if asset is not None and packages:
        asset.processing_status = "requires_repackage"
        db.add(asset)


def _validate_source(
    db: Session,
    *,
    primary: MediaAsset,
    track_type: str,
    source_media_asset_id: str | None,
    source_stream_index: int | None,
) -> None:
    if source_media_asset_id:
        source = db.get(MediaAsset, source_media_asset_id)
        if source is None:
            raise HTTPException(status_code=404, detail="source_media_asset_id not found")
        if source.upload_status != "completed":
            raise HTTPException(status_code=409, detail="Source media asset is not completed")
        if source.probed_at is None:
            raise HTTPException(status_code=409, detail="Source media asset must be probed")
        if track_type == "audio":
            if not source.audio_stream_count:
                raise HTTPException(status_code=422, detail="Source asset has no audio stream")
            settings = get_settings()
            mismatch = duration_mismatch(
                primary_seconds=primary.duration_seconds,
                track_seconds=source.duration_seconds,
                tolerance_seconds=float(settings.hls_audio_duration_tolerance_seconds),
            )
            if mismatch:
                raise HTTPException(status_code=422, detail=mismatch)
            category = (source.category or "").lower()
            if category not in {"originals", "audio", "trailers"}:
                raise HTTPException(
                    status_code=422,
                    detail="Audio track source must be an originals/audio media asset",
                )
        else:
            ext = (source.extension or "").lower().lstrip(".")
            category = (source.category or "").lower()
            if category != "subtitles" and ext not in SUBTITLE_EXTS:
                raise HTTPException(
                    status_code=422,
                    detail="Subtitle track source must be a subtitles asset (vtt/srt/ass)",
                )
        return

    if track_type == "subtitle":
        raise HTTPException(
            status_code=422,
            detail="Subtitle tracks require source_media_asset_id",
        )
    # Embedded audio on primary.
    idx = 0 if source_stream_index is None else int(source_stream_index)
    if not primary.audio_stream_count or idx >= int(primary.audio_stream_count):
        raise HTTPException(
            status_code=422,
            detail="source_stream_index is outside primary asset audio streams",
        )


def create_track(db: Session, media_asset_id: str, payload: MediaTrackCreate) -> MediaTrackOut:
    asset = db.get(MediaAsset, media_asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
    lang = _normalize_lang(payload.language_code)
    if not lang or lang not in ALLOWED_LANG:
        raise HTTPException(status_code=422, detail="Invalid language_code")
    existing = (
        db.query(MediaTrack)
        .filter(
            MediaTrack.media_asset_id == media_asset_id,
            MediaTrack.track_type == payload.track_type,
            MediaTrack.language_code == lang,
        )
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Track already exists for this language")

    _validate_source(
        db,
        primary=asset,
        track_type=payload.track_type,
        source_media_asset_id=payload.source_media_asset_id,
        source_stream_index=payload.source_stream_index,
    )

    if payload.is_default:
        _clear_default(db, media_asset_id, payload.track_type)

    row = MediaTrack(
        media_asset_id=media_asset_id,
        track_type=payload.track_type,
        language_code=lang,
        label_key=payload.label_key,
        is_default=payload.is_default,
        is_dubbed=bool(payload.is_dubbed) if payload.track_type == "audio" else False,
        source_media_asset_id=payload.source_media_asset_id,
        source_stream_index=payload.source_stream_index,
        hls_group_id=payload.hls_group_id,
        hls_name=payload.hls_name,
        sort_order=int(payload.sort_order or 0),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(row)
    _mark_packages_require_repackage(db, media_asset_id)
    db.commit()
    db.refresh(row)
    return MediaTrackOut.model_validate(row)


def update_track(db: Session, track_id: int, payload: MediaTrackUpdate) -> MediaTrackOut:
    row = db.get(MediaTrack, track_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Track not found")
    primary = db.get(MediaAsset, row.media_asset_id)
    if primary is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    data = payload.model_dump(exclude_unset=True)
    if "language_code" in data and data["language_code"] is not None:
        data["language_code"] = _normalize_lang(data["language_code"])
        if data["language_code"] not in ALLOWED_LANG:
            raise HTTPException(status_code=422, detail="Invalid language_code")
    if data.get("is_default"):
        _clear_default(db, row.media_asset_id, row.track_type)

    source_id = data.get("source_media_asset_id", row.source_media_asset_id)
    source_idx = data.get("source_stream_index", row.source_stream_index)
    if any(k in data for k in ("source_media_asset_id", "source_stream_index", "track_type")):
        _validate_source(
            db,
            primary=primary,
            track_type=row.track_type,
            source_media_asset_id=source_id,
            source_stream_index=source_idx,
        )

    for key, value in data.items():
        if key == "is_dubbed" and row.track_type != "audio":
            setattr(row, key, False)
        else:
            setattr(row, key, value)
    row.updated_at = utcnow()
    db.add(row)
    _mark_packages_require_repackage(db, row.media_asset_id)
    db.commit()
    db.refresh(row)
    return MediaTrackOut.model_validate(row)


def delete_track(db: Session, track_id: int) -> None:
    row = db.get(MediaTrack, track_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Track not found")
    asset_id = row.media_asset_id
    db.delete(row)
    _mark_packages_require_repackage(db, asset_id)
    db.commit()


def _clear_default(db: Session, media_asset_id: str, track_type: str) -> None:
    (
        db.query(MediaTrack)
        .filter(
            MediaTrack.media_asset_id == media_asset_id,
            MediaTrack.track_type == track_type,
            MediaTrack.is_default.is_(True),
        )
        .update({MediaTrack.is_default: False, MediaTrack.updated_at: utcnow()}, synchronize_session=False)
    )


def tracks_for_availability(db: Session, media_asset_id: str | None) -> list[MediaTrack]:
    if not media_asset_id:
        return []
    return (
        db.query(MediaTrack)
        .filter(MediaTrack.media_asset_id == media_asset_id)
        .order_by(MediaTrack.sort_order.asc(), MediaTrack.id.asc())
        .all()
    )
