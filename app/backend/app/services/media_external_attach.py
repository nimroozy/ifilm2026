"""Attach validated external media URLs to catalog owners (Option A: admin/demo)."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.content import Episode, Movie
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.services.media_external import ExternalMediaError, validate_external_media_url

logger = logging.getLogger("app.media_external_attach")

# Option A: direct CDN URL is returned to the player; not packaged-HLS equivalent.
PROTECTION_MODE_UNPROTECTED_DIRECT = "unprotected_direct"
EXTERNAL_POLICY = "admin_demo_only"


def mask_external_url(url: str | None) -> str | None:
    """Return a display URL with query/credentials stripped and path truncated."""
    if not url:
        return None
    parsed = urlparse(url.strip())
    host = parsed.hostname or ""
    if not host:
        return "[redacted]"
    path = parsed.path or "/"
    if len(path) > 48:
        path = f"{path[:24]}…{path[-12:]}"
    scheme = parsed.scheme or "https"
    return f"{scheme}://{host}{path}"


def media_asset_to_out(asset: MediaAsset) -> dict:
    """Serialize asset for API; mask external_url (never expose query tokens)."""
    data = {
        c.key: getattr(asset, c.key)
        for c in asset.__table__.columns
        if c.key != "external_acknowledged_by_admin_id"
    }
    raw = data.get("external_url")
    masked = mask_external_url(raw) if raw else None
    data["external_url"] = masked
    data["external_url_masked"] = masked
    return data


def is_external_playable(asset: MediaAsset) -> bool:
    return (
        getattr(asset, "source_type", "uploaded") == "external"
        and bool(getattr(asset, "external_url", None))
        and getattr(asset, "external_validated_at", None) is not None
        and asset.upload_status == "completed"
        and bool(getattr(asset, "external_is_primary", False))
    )


def _deactivate_primary_externals(
    db: Session,
    *,
    movie_id: int | None,
    episode_id: int | None,
    except_id: str | None = None,
) -> int:
    q = db.query(MediaAsset).filter(
        MediaAsset.source_type == "external",
        MediaAsset.external_is_primary.is_(True),
    )
    if movie_id is not None:
        q = q.filter(MediaAsset.movie_id == movie_id)
    elif episode_id is not None:
        q = q.filter(MediaAsset.episode_id == episode_id)
    else:
        return 0
    if except_id:
        q = q.filter(MediaAsset.id != except_id)
    updated = 0
    for asset in q.with_for_update().all():
        asset.external_is_primary = False
        asset.updated_at = utcnow()
        db.add(asset)
        updated += 1
    return updated


def attach_external_media(
    db: Session,
    *,
    url: str,
    movie_id: int | None = None,
    episode_id: int | None = None,
    admin_id: int | None = None,
    category: str = "originals",
    acknowledge_unprotected_external: bool = False,
) -> MediaAsset:
    if (movie_id is None) == (episode_id is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide exactly one of movie_id or episode_id",
        )
    if not acknowledge_unprotected_external:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "External media is unprotected (Option A: admin/demo only). "
                "Set acknowledge_unprotected_external=true to confirm."
            ),
        )
    if movie_id is not None and db.get(Movie, movie_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    if episode_id is not None and db.get(Episode, episode_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    try:
        validated = validate_external_media_url(url)
    except ExternalMediaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    path = urlparse(validated.url).path
    name = path.rsplit("/", 1)[-1] or f"external.{validated.kind}"
    ext = ""
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()[:32]

    deactivated = _deactivate_primary_externals(db, movie_id=movie_id, episode_id=episode_id)
    now = utcnow()
    asset = MediaAsset(
        id=new_uuid(),
        movie_id=movie_id,
        episode_id=episode_id,
        original_filename=name[:512],
        stored_filename="",
        mime_type=validated.content_type
        or ("application/vnd.apple.mpegurl" if validated.kind == "hls" else "video/mp4"),
        extension=ext,
        size_bytes=int(validated.content_length or 0),
        storage_backend="external",
        storage_path=None,
        category=category,
        upload_status="completed",
        processing_status="ready",
        source_type="external",
        external_url=validated.url,
        external_kind=validated.kind,
        external_content_type=validated.content_type,
        external_content_length=validated.content_length,
        external_accept_ranges=validated.accept_ranges,
        external_validated_at=validated.validated_at,
        external_is_primary=True,
        external_protection_mode=PROTECTION_MODE_UNPROTECTED_DIRECT,
        external_acknowledged_at=now,
        external_acknowledged_by_admin_id=admin_id,
        created_by_admin_id=admin_id,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    logger.info(
        "media_external event=attached details=%s",
        {
            "asset_id": asset.id,
            "movie_id": movie_id,
            "episode_id": episode_id,
            "admin_id": admin_id,
            "kind": validated.kind,
            "protection_mode": PROTECTION_MODE_UNPROTECTED_DIRECT,
            "policy": EXTERNAL_POLICY,
            "deactivated_primaries": deactivated,
            "url_display": mask_external_url(validated.url),
        },
    )
    return asset
