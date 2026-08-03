"""Attach / detach media assets to catalog owners without deleting media."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.content import Episode, Movie
from app.models.media_assets import MediaAsset, utcnow
from app.services.streaming.sessions import revoke_sessions_for_asset

logger = logging.getLogger("app.media_linking")

OwnerType = Literal["movie", "episode"]

VIDEO_MIME_PREFIXES = ("video/",)
LINKABLE_CATEGORIES = frozenset({"originals", "trailers"})
UNUSABLE_UPLOAD = frozenset({"failed", "cancelled", "deleted"})


def _audit(event: str, **fields: object) -> None:
    safe = {k: v for k, v in fields.items() if k not in {"storage_path", "token", "path"}}
    logger.info("media_linking event=%s details=%s", event, safe)


def _owners_set(asset: MediaAsset) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    if asset.movie_id is not None:
        out.append(("movie", asset.movie_id))
    if asset.series_id is not None:
        out.append(("series", asset.series_id))
    if asset.season_id is not None:
        out.append(("season", asset.season_id))
    if asset.episode_id is not None:
        out.append(("episode", asset.episode_id))
    return out


def _is_unassigned(asset: MediaAsset) -> bool:
    return not _owners_set(asset)


def _get_asset_for_update(db: Session, asset_id: str) -> MediaAsset:
    asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.id == asset_id)
        .with_for_update()
        .first()
    )
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
    return asset


def _require_movie(db: Session, movie_id: int) -> Movie:
    movie = db.query(Movie).filter(Movie.id == movie_id).first()
    if movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    return movie


def _require_episode(db: Session, episode_id: int) -> Episode:
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if episode is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    return episode


def _assert_linkable_video(asset: MediaAsset) -> None:
    if asset.upload_status in UNUSABLE_UPLOAD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Media asset upload status is {asset.upload_status}",
        )
    if asset.category not in LINKABLE_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {', '.join(sorted(LINKABLE_CATEGORIES))} assets can be linked as playable media",
        )
    mime = (asset.mime_type or "").lower()
    if not any(mime.startswith(prefix) for prefix in VIDEO_MIME_PREFIXES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only video assets can be linked to movies or episodes",
        )


def attach_asset(
    db: Session,
    *,
    asset_id: str,
    owner_type: OwnerType,
    owner_id: int,
    admin_id: int | None,
) -> MediaAsset:
    """Atomically assign an unassigned asset to a movie or episode."""
    if owner_type not in {"movie", "episode"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="owner_type must be movie or episode",
        )

    asset = _get_asset_for_update(db, asset_id)
    _assert_linkable_video(asset)

    if owner_type == "movie":
        _require_movie(db, owner_id)
        target_movie_id, target_episode_id = owner_id, None
    else:
        _require_episode(db, owner_id)
        target_movie_id, target_episode_id = None, owner_id

    owners = _owners_set(asset)
    if owners:
        # Idempotent same-owner attach.
        if owner_type == "movie" and owners == [("movie", owner_id)]:
            return asset
        if owner_type == "episode" and owners == [("episode", owner_id)]:
            return asset
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Media asset is already assigned to another owner",
        )

    asset.movie_id = target_movie_id
    asset.series_id = None
    asset.season_id = None
    asset.episode_id = target_episode_id
    asset.updated_at = utcnow()
    db.add(asset)
    db.commit()
    db.refresh(asset)
    _audit(
        "media_asset_attached",
        asset_id=asset.id,
        owner_type=owner_type,
        owner_id=owner_id,
        admin_id=admin_id,
    )
    return asset


def detach_asset(
    db: Session,
    *,
    asset_id: str,
    admin_id: int | None,
    force_unpublish: bool = False,
) -> MediaAsset:
    """Remove ownership association only. Never deletes media or packages."""
    asset = _get_asset_for_update(db, asset_id)
    owners = _owners_set(asset)
    if not owners:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Media asset is not linked to any owner",
        )

    movie: Movie | None = None
    episode: Episode | None = None
    if asset.movie_id is not None:
        movie = _require_movie(db, asset.movie_id)
    elif asset.episode_id is not None:
        episode = _require_episode(db, asset.episode_id)
    else:
        # series/season-only assets: allow detach without publish gate
        pass

    published_entity: Movie | Episode | None = None
    if movie is not None and movie.status == "published":
        published_entity = movie
    elif episode is not None and episode.status == "published":
        published_entity = episode

    if published_entity is not None:
        from app.services.streaming.activation import get_active_completed_package

        owner_filter = (
            MediaAsset.movie_id == asset.movie_id
            if asset.movie_id is not None
            else MediaAsset.episode_id == asset.episode_id
        )
        other_assets = (
            db.query(MediaAsset)
            .filter(
                MediaAsset.id != asset.id,
                owner_filter,
                MediaAsset.upload_status.notin_(list(UNUSABLE_UPLOAD)),
            )
            .all()
        )
        remaining_playable = any(
            get_active_completed_package(db, other.id) is not None for other in other_assets
        )
        if not remaining_playable:
            if force_unpublish:
                published_entity.status = "unpublished"
                if hasattr(published_entity, "unpublished_at"):
                    published_entity.unpublished_at = utcnow()
                db.add(published_entity)
                _audit(
                    "content_unpublished_for_detach",
                    entity_type="movie" if movie else "episode",
                    entity_id=published_entity.id,
                    asset_id=asset.id,
                    admin_id=admin_id,
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Cannot detach the only playable media from published content. "
                        "Unpublish first, attach a replacement, or pass force_unpublish=true."
                    ),
                )

    previous = {
        "movie_id": asset.movie_id,
        "series_id": asset.series_id,
        "season_id": asset.season_id,
        "episode_id": asset.episode_id,
    }
    asset.movie_id = None
    asset.series_id = None
    asset.season_id = None
    asset.episode_id = None
    asset.updated_at = utcnow()
    db.add(asset)
    db.commit()
    db.refresh(asset)

    revoked = revoke_sessions_for_asset(
        db, media_asset_id=asset.id, reason="media_asset_detached"
    )
    _audit(
        "media_asset_detached",
        asset_id=asset.id,
        previous=previous,
        admin_id=admin_id,
        sessions_revoked=revoked,
    )
    return asset


def list_assets_query(
    db: Session,
    *,
    status_filter: str | None = None,
    movie_id: int | None = None,
    episode_id: int | None = None,
    unassigned: bool | None = None,
    category: str | None = None,
    q: str | None = None,
    video_only: bool = False,
    linkable_only: bool = False,
):
    query = db.query(MediaAsset)
    if status_filter:
        query = query.filter(MediaAsset.upload_status == status_filter)
    else:
        query = query.filter(MediaAsset.upload_status != "deleted")

    if movie_id is not None:
        query = query.filter(MediaAsset.movie_id == movie_id)
    if episode_id is not None:
        query = query.filter(MediaAsset.episode_id == episode_id)
    if unassigned is True:
        query = query.filter(
            and_(
                MediaAsset.movie_id.is_(None),
                MediaAsset.series_id.is_(None),
                MediaAsset.season_id.is_(None),
                MediaAsset.episode_id.is_(None),
            )
        )
    elif unassigned is False:
        query = query.filter(
            or_(
                MediaAsset.movie_id.is_not(None),
                MediaAsset.series_id.is_not(None),
                MediaAsset.season_id.is_not(None),
                MediaAsset.episode_id.is_not(None),
            )
        )
    if category:
        query = query.filter(MediaAsset.category == category)
    if linkable_only:
        query = query.filter(MediaAsset.category.in_(list(LINKABLE_CATEGORIES)))
    if video_only:
        query = query.filter(MediaAsset.mime_type.ilike("video/%"))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                MediaAsset.original_filename.ilike(like),
                MediaAsset.id.ilike(like),
                MediaAsset.checksum_sha256.ilike(like),
            )
        )
    return query
