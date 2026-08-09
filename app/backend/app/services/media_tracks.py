"""CRUD helpers for media_tracks."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.media_assets import MediaAsset
from app.models.media_tracks import MediaTrack, utcnow
from app.schemas.media_tracks import MediaTrackCreate, MediaTrackListOut, MediaTrackOut, MediaTrackUpdate

ALLOWED_LANG = frozenset({"en", "fa", "ps", "prs", "ar", "hi", "ur", "tr", "ru", "ko", "ja", "zh"})


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


def create_track(db: Session, media_asset_id: str, payload: MediaTrackCreate) -> MediaTrackOut:
    asset = db.get(MediaAsset, media_asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
    lang = _normalize_lang(payload.language_code)
    if not lang:
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

    if payload.is_default:
        _clear_default(db, media_asset_id, payload.track_type)

    row = MediaTrack(
        media_asset_id=media_asset_id,
        track_type=payload.track_type,
        language_code=lang,
        label_key=payload.label_key,
        is_default=payload.is_default,
        is_dubbed=bool(payload.is_dubbed) if payload.track_type == "audio" else False,
        hls_group_id=payload.hls_group_id,
        hls_name=payload.hls_name,
        sort_order=int(payload.sort_order or 0),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return MediaTrackOut.model_validate(row)


def update_track(db: Session, track_id: int, payload: MediaTrackUpdate) -> MediaTrackOut:
    row = db.get(MediaTrack, track_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Track not found")
    data = payload.model_dump(exclude_unset=True)
    if "language_code" in data and data["language_code"] is not None:
        data["language_code"] = _normalize_lang(data["language_code"])
    if data.get("is_default"):
        _clear_default(db, row.media_asset_id, row.track_type)
    for key, value in data.items():
        if key == "is_dubbed" and row.track_type != "audio":
            setattr(row, key, False)
        else:
            setattr(row, key, value)
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return MediaTrackOut.model_validate(row)


def delete_track(db: Session, track_id: int) -> None:
    row = db.get(MediaTrack, track_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Track not found")
    db.delete(row)
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
