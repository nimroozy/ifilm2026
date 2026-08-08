"""Subscriber watchlist service (movie XOR series)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.content import Movie, Series
from app.models.user import Subscriber, WatchlistItem
from app.schemas.watchlist import WatchlistAddIn, WatchlistItemOut
from app.services.publishing.visibility import movie_is_public, series_is_public


def utcnow() -> datetime:
    return datetime.now(UTC)


def _serialize(db: Session, row: WatchlistItem) -> WatchlistItemOut:
    if row.movie_id is not None:
        movie = db.get(Movie, row.movie_id)
        available = bool(movie and movie_is_public(movie))
        if available and movie:
            return WatchlistItemOut(
                id=row.id,
                content_type="movie",
                movie_id=row.movie_id,
                series_id=None,
                title=movie.title,
                poster_url=movie.poster_url or "",
                backdrop_url=movie.backdrop_url or "",
                release_year=movie.release_year,
                available=True,
                detail_path=f"/movie/{movie.slug}",
                player_path=f"/player/movie/{movie.id}",
                created_at=row.created_at,
            )
        return WatchlistItemOut(
            id=row.id,
            content_type="movie",
            movie_id=row.movie_id,
            series_id=None,
            title="Unavailable",
            available=False,
            created_at=row.created_at,
        )

    series = db.get(Series, row.series_id) if row.series_id is not None else None
    available = bool(series and series_is_public(series))
    if available and series:
        return WatchlistItemOut(
            id=row.id,
            content_type="series",
            movie_id=None,
            series_id=row.series_id,
            title=series.title,
            poster_url=series.poster_url or "",
            backdrop_url=series.backdrop_url or "",
            release_year=series.release_year,
            available=True,
            detail_path=f"/series/{series.slug}",
            player_path="",
            created_at=row.created_at,
        )
    return WatchlistItemOut(
        id=row.id,
        content_type="series",
        movie_id=None,
        series_id=row.series_id,
        title="Unavailable",
        available=False,
        created_at=row.created_at,
    )


def list_watchlist(
    db: Session,
    subscriber: Subscriber,
    *,
    page: int = 1,
    page_size: int = 40,
) -> tuple[list[WatchlistItemOut], int]:
    q = db.query(WatchlistItem).filter(WatchlistItem.subscriber_id == subscriber.id)
    total = q.count()
    rows = (
        q.order_by(WatchlistItem.created_at.desc(), WatchlistItem.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [_serialize(db, row) for row in rows], total


def membership(
    db: Session,
    subscriber: Subscriber,
    *,
    movie_id: int | None = None,
    series_id: int | None = None,
) -> tuple[bool, int | None]:
    if (movie_id is None) == (series_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Exactly one of movie_id or series_id is required",
        )
    q = db.query(WatchlistItem).filter(WatchlistItem.subscriber_id == subscriber.id)
    if movie_id is not None:
        q = q.filter(WatchlistItem.movie_id == movie_id)
    else:
        q = q.filter(WatchlistItem.series_id == series_id)
    row = q.first()
    if row is None:
        return False, None
    return True, row.id


def add_item(db: Session, subscriber: Subscriber, payload: WatchlistAddIn) -> WatchlistItemOut:
    if payload.movie_id is not None:
        movie = db.get(Movie, payload.movie_id)
        if movie is None or getattr(movie, "deleted_at", None) is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
        existing = (
            db.query(WatchlistItem)
            .filter(
                WatchlistItem.subscriber_id == subscriber.id,
                WatchlistItem.movie_id == payload.movie_id,
            )
            .first()
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "duplicate_membership", "message": "Already in watchlist"},
            )
        row = WatchlistItem(
            subscriber_id=subscriber.id,
            movie_id=payload.movie_id,
            series_id=None,
            created_at=utcnow(),
        )
    else:
        series = db.get(Series, payload.series_id)
        if series is None or getattr(series, "deleted_at", None) is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
        existing = (
            db.query(WatchlistItem)
            .filter(
                WatchlistItem.subscriber_id == subscriber.id,
                WatchlistItem.series_id == payload.series_id,
            )
            .first()
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "duplicate_membership", "message": "Already in watchlist"},
            )
        row = WatchlistItem(
            subscriber_id=subscriber.id,
            movie_id=None,
            series_id=payload.series_id,
            created_at=utcnow(),
        )

    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "duplicate_membership", "message": "Already in watchlist"},
        ) from exc
    from app.services.recommendations.cache import invalidate_user_recommendation_cache

    invalidate_user_recommendation_cache(subscriber.id)
    return _serialize(db, row)


def remove_item(db: Session, subscriber: Subscriber, item_id: int) -> int:
    deleted = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.subscriber_id == subscriber.id, WatchlistItem.id == item_id)
        .delete(synchronize_session=False)
    )
    if deleted:
        from app.services.recommendations.cache import invalidate_user_recommendation_cache

        invalidate_user_recommendation_cache(subscriber.id)
    return int(deleted)


def remove_by_content(
    db: Session,
    subscriber: Subscriber,
    *,
    movie_id: int | None = None,
    series_id: int | None = None,
) -> int:
    if (movie_id is None) == (series_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Exactly one of movie_id or series_id is required",
        )
    q = db.query(WatchlistItem).filter(WatchlistItem.subscriber_id == subscriber.id)
    if movie_id is not None:
        q = q.filter(WatchlistItem.movie_id == movie_id)
    else:
        q = q.filter(WatchlistItem.series_id == series_id)
    deleted = int(q.delete(synchronize_session=False))
    if deleted:
        from app.services.recommendations.cache import invalidate_user_recommendation_cache

        invalidate_user_recommendation_cache(subscriber.id)
    return deleted


def clear_all(db: Session, subscriber: Subscriber) -> int:
    deleted = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.subscriber_id == subscriber.id)
        .delete(synchronize_session=False)
    )
    if deleted:
        from app.services.recommendations.cache import invalidate_user_recommendation_cache

        invalidate_user_recommendation_cache(subscriber.id)
    return int(deleted)


def count_items(db: Session, subscriber: Subscriber) -> int:
    return db.query(WatchlistItem).filter(WatchlistItem.subscriber_id == subscriber.id).count()
