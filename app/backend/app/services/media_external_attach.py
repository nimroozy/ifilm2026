"""Attach validated external media URLs to catalog owners."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.content import Episode, Movie
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.services.media_external import ExternalMediaError, validate_external_media_url


def attach_external_media(
    db: Session,
    *,
    url: str,
    movie_id: int | None = None,
    episode_id: int | None = None,
    admin_id: int | None = None,
    category: str = "originals",
) -> MediaAsset:
    if (movie_id is None) == (episode_id is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide exactly one of movie_id or episode_id",
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
        created_by_admin_id=admin_id,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def is_external_playable(asset: MediaAsset) -> bool:
    return (
        getattr(asset, "source_type", "uploaded") == "external"
        and bool(getattr(asset, "external_url", None))
        and getattr(asset, "external_validated_at", None) is not None
        and asset.upload_status == "completed"
    )
