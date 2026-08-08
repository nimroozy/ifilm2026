"""Persistent watch progress service for authenticated subscribers."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.models.content import Episode, Movie
from app.models.media_assets import MediaAsset
from app.models.media_playback import PRINCIPAL_SUBSCRIBER, MediaPlaybackSession
from app.models.user import Subscriber
from app.models.watch_progress import UserWatchProgress
from app.schemas.watch_history import WatchProgressOut, WatchProgressUpdate
from app.services.publishing.visibility import (
    episode_is_public,
    is_publicly_visible_entity,
    movie_is_public,
)
from app.services.streaming.activation import get_active_completed_package


def utcnow() -> datetime:
    return datetime.now(UTC)


def _percent(position: float, duration: float) -> float:
    if duration <= 0:
        return 0.0
    return round(min(100.0, max(0.0, (position / duration) * 100.0)), 2)


def _resolve_duration(db: Session, asset: MediaAsset, client_duration: float | None) -> float:
    package = get_active_completed_package(db, asset.id)
    candidates: list[float] = []
    if package is not None and package.duration_seconds and package.duration_seconds > 0:
        candidates.append(float(package.duration_seconds))
    if asset.duration_seconds and asset.duration_seconds > 0:
        candidates.append(float(asset.duration_seconds))
    if client_duration and client_duration > 0 and not math.isnan(client_duration) and not math.isinf(client_duration):
        # Accept client duration only as last resort / sanity fill when probe missing.
        if not candidates:
            candidates.append(float(client_duration))
        else:
            # Prefer server duration; ignore wildly different client values.
            server = candidates[0]
            if abs(client_duration - server) / max(server, 1.0) < 0.35:
                pass
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "duration_unknown", "message": "Media duration is unavailable"},
        )
    return candidates[0]


def _get_asset_for_subscriber(db: Session, asset_id: str) -> MediaAsset:
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    if asset.movie_id is None and asset.episode_id is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "not_playable_content", "message": "Asset is not linked to a movie or episode"},
        )
    if asset.movie_id is not None and asset.episode_id is not None:
        raise HTTPException(
            status_code=400,
            detail={"code": "ambiguous_owner", "message": "Asset has ambiguous catalog ownership"},
        )
    return asset


def _validate_session(
    db: Session,
    *,
    subscriber: Subscriber,
    asset_id: str,
    playback_session_id: str | None,
) -> None:
    if not playback_session_id:
        return
    session = db.get(MediaPlaybackSession, playback_session_id)
    if session is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_session", "message": "Playback session not found"},
        )
    if session.principal_type != PRINCIPAL_SUBSCRIBER or session.principal_id != str(subscriber.id):
        raise HTTPException(
            status_code=403,
            detail={"code": "session_forbidden", "message": "Playback session does not belong to user"},
        )
    if session.media_asset_id != asset_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "session_asset_mismatch", "message": "Playback session asset mismatch"},
        )


def _content_available(db: Session, asset: MediaAsset) -> bool:
    if asset.upload_status != "completed":
        return False
    if get_active_completed_package(db, asset.id) is None:
        return False
    if asset.movie_id is not None:
        movie = db.get(Movie, asset.movie_id)
        return movie_is_public(movie) if movie else False
    if asset.episode_id is not None:
        episode = db.get(Episode, asset.episode_id)
        return episode_is_public(db, episode) if episode else False
    return False


def _serialize(
    db: Session,
    row: UserWatchProgress,
    *,
    settings: Settings,
    include_unpublished_metadata: bool = False,
) -> WatchProgressOut:
    asset = db.get(MediaAsset, row.media_asset_id)
    available = bool(asset and _content_available(db, asset))
    content_type: str = "movie" if row.movie_id is not None else "episode"
    title = ""
    subtitle = ""
    poster = ""
    series_id = None
    season_number = None
    episode_number = None
    player_path = ""

    if available or include_unpublished_metadata:
        if row.movie_id is not None:
            movie = db.get(Movie, row.movie_id)
            if movie and (available or include_unpublished_metadata):
                if available or is_publicly_visible_entity(movie):
                    title = movie.title
                    poster = movie.poster_url or ""
                elif available is False:
                    title = "Unavailable"
                player_path = f"/player/movie/{movie.id}"
        elif row.episode_id is not None:
            episode = (
                db.query(Episode)
                .options(joinedload(Episode.season), joinedload(Episode.series))
                .filter(Episode.id == row.episode_id)
                .first()
            )
            if episode:
                series_id = episode.series_id
                season_number = episode.season.season_number if episode.season else None
                episode_number = episode.episode_number
                player_path = f"/player/episode/{episode.id}"
                if available:
                    title = episode.title
                    if episode.series:
                        subtitle = f"S{season_number} E{episode_number}" if season_number else f"E{episode_number}"
                        poster = episode.thumbnail_url or episode.series.poster_url or ""
                        if not title:
                            title = episode.series.title
                else:
                    title = "Unavailable"
                    subtitle = ""
                    poster = ""
    else:
        title = "Unavailable"
        poster = ""
        player_path = ""

    return WatchProgressOut(
        id=row.id,
        media_asset_id=row.media_asset_id,
        content_type=content_type,  # type: ignore[arg-type]
        movie_id=row.movie_id,
        episode_id=row.episode_id,
        series_id=series_id,
        season_number=season_number,
        episode_number=episode_number,
        title=title,
        subtitle=subtitle,
        poster_url=poster,
        position_seconds=row.position_seconds,
        duration_seconds=row.duration_seconds,
        progress_percent=row.progress_percent,
        completed=row.completed,
        available=available,
        player_path=player_path if available else "",
        first_watched_at=row.first_watched_at,
        last_watched_at=row.last_watched_at,
        completed_at=row.completed_at,
        last_event_at=row.last_event_at,
    )


def get_progress(db: Session, subscriber: Subscriber, asset_id: str) -> WatchProgressOut | None:
    row = (
        db.query(UserWatchProgress)
        .filter(
            UserWatchProgress.subscriber_id == subscriber.id,
            UserWatchProgress.media_asset_id == asset_id,
        )
        .first()
    )
    if row is None:
        return None
    return _serialize(db, row, settings=get_settings())


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def upsert_progress(
    db: Session,
    subscriber: Subscriber,
    asset_id: str,
    payload: WatchProgressUpdate,
    *,
    force_complete: bool = False,
) -> WatchProgressOut:
    settings = get_settings()
    asset = _get_asset_for_subscriber(db, asset_id)
    _validate_session(
        db,
        subscriber=subscriber,
        asset_id=asset_id,
        playback_session_id=payload.playback_session_id,
    )
    duration = _resolve_duration(db, asset, payload.duration_seconds)
    margin = float(settings.watch_progress_resume_margin_seconds)
    max_pos = max(0.0, duration - margin) if duration > margin else duration
    position = 0.0 if payload.start_over else min(float(payload.position_seconds), max_pos)
    if payload.start_over:
        position = 0.0

    event_at = payload.event_at or utcnow()
    if event_at.tzinfo is None:
        raise HTTPException(status_code=400, detail="event_at must be timezone-aware")
    event_at = event_at.astimezone(UTC)

    row = (
        db.query(UserWatchProgress)
        .filter(
            UserWatchProgress.subscriber_id == subscriber.id,
            UserWatchProgress.media_asset_id == asset_id,
        )
        .with_for_update()
        .first()
    )

    # Also try logical unique by movie/episode if asset rotated.
    if row is None:
        if asset.movie_id is not None:
            row = (
                db.query(UserWatchProgress)
                .filter(
                    UserWatchProgress.subscriber_id == subscriber.id,
                    UserWatchProgress.movie_id == asset.movie_id,
                )
                .with_for_update()
                .first()
            )
        elif asset.episode_id is not None:
            row = (
                db.query(UserWatchProgress)
                .filter(
                    UserWatchProgress.subscriber_id == subscriber.id,
                    UserWatchProgress.episode_id == asset.episode_id,
                )
                .with_for_update()
                .first()
            )
        if row is not None:
            row.media_asset_id = asset_id

    if row is not None and event_at < _as_utc(row.last_event_at) and not payload.start_over:
        # Stale update — return current state without mutation.
        return _serialize(db, row, settings=settings)

    percent = _percent(position, duration)
    complete_threshold = float(settings.watch_progress_complete_percent)
    completed = bool(force_complete or payload.start_over is False and percent >= complete_threshold)
    if payload.start_over:
        completed = False

    now = utcnow()
    if row is None:
        row = UserWatchProgress(
            subscriber_id=subscriber.id,
            media_asset_id=asset_id,
            movie_id=asset.movie_id,
            episode_id=asset.episode_id,
            playback_session_id=payload.playback_session_id,
            device_id=payload.device_id,
            position_seconds=position,
            duration_seconds=duration,
            progress_percent=percent,
            completed=completed,
            first_watched_at=now,
            last_watched_at=now,
            completed_at=now if completed else None,
            last_event_at=event_at,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        # Never let a non-start-over stale or partial update clear completion once set,
        # unless this event is newer and explicitly starts over (handled above).
        if row.completed and not payload.start_over and not force_complete:
            # Allow position updates only if not rolling completion back via lower percent
            # from a newer event — completion sticks unless Start Over.
            completed = True
            position = max(position, row.position_seconds) if event_at >= row.last_event_at else row.position_seconds
            percent = _percent(position, duration)

        row.media_asset_id = asset_id
        row.movie_id = asset.movie_id
        row.episode_id = asset.episode_id
        row.playback_session_id = payload.playback_session_id or row.playback_session_id
        if payload.device_id is not None:
            row.device_id = payload.device_id
        row.position_seconds = position
        row.duration_seconds = duration
        row.progress_percent = percent if not (row.completed and not payload.start_over) else max(row.progress_percent, percent)
        row.completed = completed
        if completed and row.completed_at is None:
            row.completed_at = now
        if payload.start_over:
            row.completed_at = None
            row.progress_percent = 0.0
            row.position_seconds = 0.0
            row.completed = False
        row.last_watched_at = now
        row.last_event_at = event_at
        row.updated_at = now
        # Resume / new progress brings the title back onto Continue Watching.
        if not completed and not payload.start_over:
            row.hidden_from_continue = False
        if payload.start_over:
            row.hidden_from_continue = False
        db.add(row)

    db.flush()
    from app.services.recommendations.cache import invalidate_user_recommendation_cache

    invalidate_user_recommendation_cache(subscriber.id)
    return _serialize(db, row, settings=settings)


def mark_complete(db: Session, subscriber: Subscriber, asset_id: str, payload: WatchProgressUpdate) -> WatchProgressOut:
    payload = payload.model_copy(update={"start_over": False})
    return upsert_progress(db, subscriber, asset_id, payload, force_complete=True)


def list_continue_watching(
    db: Session, subscriber: Subscriber, *, limit: int | None = None
) -> list[WatchProgressOut]:
    settings = get_settings()
    limit = limit or settings.continue_watching_limit
    min_seconds = float(settings.watch_progress_min_seconds)
    rows = (
        db.query(UserWatchProgress)
        .filter(
            UserWatchProgress.subscriber_id == subscriber.id,
            UserWatchProgress.completed.is_(False),
            UserWatchProgress.hidden_from_continue.is_(False),
            UserWatchProgress.position_seconds >= min_seconds,
        )
        .order_by(UserWatchProgress.last_watched_at.desc(), UserWatchProgress.id.desc())
        .limit(limit * 3)  # over-fetch then filter availability
        .all()
    )
    out: list[WatchProgressOut] = []
    for row in rows:
        item = _serialize(db, row, settings=settings)
        if item.available and not item.completed and item.position_seconds >= min_seconds:
            out.append(item)
        if len(out) >= limit:
            break
    return out


def list_history(
    db: Session,
    subscriber: Subscriber,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[WatchProgressOut], int]:
    settings = get_settings()
    q = db.query(UserWatchProgress).filter(UserWatchProgress.subscriber_id == subscriber.id)
    total = q.count()
    rows = (
        q.order_by(UserWatchProgress.last_watched_at.desc(), UserWatchProgress.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [_serialize(db, row, settings=settings) for row in rows], total


def delete_one(db: Session, subscriber: Subscriber, asset_id: str) -> int:
    deleted = (
        db.query(UserWatchProgress)
        .filter(
            UserWatchProgress.subscriber_id == subscriber.id,
            UserWatchProgress.media_asset_id == asset_id,
        )
        .delete(synchronize_session=False)
    )
    if deleted:
        from app.services.recommendations.cache import invalidate_user_recommendation_cache

        invalidate_user_recommendation_cache(subscriber.id)
    return int(deleted)


def delete_all(db: Session, subscriber: Subscriber) -> int:
    deleted = (
        db.query(UserWatchProgress)
        .filter(UserWatchProgress.subscriber_id == subscriber.id)
        .delete(synchronize_session=False)
    )
    if deleted:
        from app.services.recommendations.cache import invalidate_user_recommendation_cache

        invalidate_user_recommendation_cache(subscriber.id)
    return int(deleted)


def dismiss_continue_watching(db: Session, subscriber: Subscriber, asset_id: str) -> int:
    """Hide from Continue Watching without deleting watch history."""
    row = (
        db.query(UserWatchProgress)
        .filter(
            UserWatchProgress.subscriber_id == subscriber.id,
            UserWatchProgress.media_asset_id == asset_id,
        )
        .first()
    )
    if row is None:
        return 0
    row.hidden_from_continue = True
    row.updated_at = utcnow()
    db.add(row)
    db.flush()
    from app.services.recommendations.cache import invalidate_user_recommendation_cache

    invalidate_user_recommendation_cache(subscriber.id)
    return 1
