"""Resolve a playable media asset (active HLS package or primary external URL)."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.media_assets import MediaAsset
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage
from app.services.media_external_attach import is_external_playable
from app.services.streaming.activation import get_active_completed_package


def get_playable_asset_by_id(db: Session, media_asset_id: str) -> MediaAsset:
    asset = db.get(MediaAsset, media_asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
    if is_external_playable(asset):
        return asset
    if asset.upload_status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Media asset upload is not completed",
        )
    package = get_active_completed_package(db, asset.id)
    if package is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active completed HLS package for this asset",
        )
    return asset


def get_playable_asset_for_content(
    db: Session, *, content_type: str, content_id: int
) -> MediaAsset:
    """Map catalog movie/episode id → playable media asset (package preferred, else primary external)."""
    normalized = (content_type or "").strip().lower()
    if normalized not in {"movie", "episode"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="content_type must be movie or episode",
        )

    # Prefer packaged HLS for production playback when available.
    query = (
        db.query(MediaAsset)
        .join(MediaPackage, MediaPackage.media_asset_id == MediaAsset.id)
        .options(joinedload(MediaAsset.packages))
        .filter(
            MediaAsset.upload_status == "completed",
            MediaAsset.source_type != "external",
            MediaPackage.package_type == PACKAGE_TYPE_HLS_VOD,
            MediaPackage.status == "completed",
            MediaPackage.is_active.is_(True),
        )
    )
    if normalized == "movie":
        query = query.filter(MediaAsset.movie_id == content_id)
    else:
        query = query.filter(MediaAsset.episode_id == content_id)

    asset = query.order_by(MediaAsset.updated_at.desc(), MediaAsset.id.desc()).first()
    if asset is not None:
        return asset

    # Fallback: single primary validated external (Option A admin/demo path).
    external_q = db.query(MediaAsset).filter(
        MediaAsset.upload_status == "completed",
        MediaAsset.source_type == "external",
        MediaAsset.external_url.isnot(None),
        MediaAsset.external_validated_at.isnot(None),
        MediaAsset.external_is_primary.is_(True),
    )
    if normalized == "movie":
        external_q = external_q.filter(MediaAsset.movie_id == content_id)
    else:
        external_q = external_q.filter(MediaAsset.episode_id == content_id)
    external = external_q.order_by(
        MediaAsset.external_validated_at.desc(),
        MediaAsset.updated_at.desc(),
        MediaAsset.id.desc(),
    ).first()
    if external is not None:
        return external

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="No playable active HLS package for this content",
    )
