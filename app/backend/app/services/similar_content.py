"""Ranked similar movies for detail pages (catalog-only, no fake rows)."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.models.collections import Collection, CollectionItem
from app.models.content import Movie, movie_genres
from app.schemas.content import MovieOut
from app.services.catalog import movie_out
from app.services.publishing.visibility import apply_public_visibility
from app.services.tmdb.client import TMDBClient, TMDBClientError


def _published_movies(db: Session):
    return apply_public_visibility(db.query(Movie).options(selectinload(Movie.genre_links)), Movie)


def _from_collections(db: Session, movie: Movie, *, limit: int, exclude: set[int]) -> list[Movie]:
    collection_ids = [
        row[0]
        for row in db.query(CollectionItem.collection_id)
        .join(Collection, Collection.id == CollectionItem.collection_id)
        .filter(
            CollectionItem.movie_id == movie.id,
            Collection.deleted_at.is_(None),
            Collection.status == "published",
        )
        .distinct()
        .all()
    ]
    if not collection_ids:
        return []
    q = (
        _published_movies(db)
        .join(CollectionItem, CollectionItem.movie_id == Movie.id)
        .filter(
            CollectionItem.collection_id.in_(collection_ids),
            Movie.id != movie.id,
            Movie.id.notin_(exclude) if exclude else True,
        )
        .order_by(CollectionItem.position.asc(), Movie.id.desc())
        .limit(limit)
    )
    return list(q.all())


def _from_genres(db: Session, movie: Movie, *, limit: int, exclude: set[int]) -> list[Movie]:
    genre_ids = [g.id for g in (movie.genre_links or [])]
    if not genre_ids:
        return []
    q = (
        _published_movies(db)
        .join(movie_genres, movie_genres.c.movie_id == Movie.id)
        .filter(
            movie_genres.c.genre_id.in_(genre_ids),
            Movie.id != movie.id,
        )
    )
    if exclude:
        q = q.filter(Movie.id.notin_(exclude))
    q = (
        q.group_by(Movie.id)
        .order_by(func.count(movie_genres.c.genre_id).desc(), Movie.views.desc(), Movie.id.desc())
        .limit(limit)
    )
    return list(q.all())


def _from_tmdb_similar(
    db: Session,
    movie: Movie,
    *,
    settings: Settings,
    limit: int,
    exclude: set[int],
    client: TMDBClient | None,
) -> list[Movie]:
    if not movie.tmdb_id:
        return []
    client = client or TMDBClient(settings)
    if not client.enabled:
        return []
    try:
        payload = client.movie_similar(int(movie.tmdb_id), page=1)
    except TMDBClientError:
        return []
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []
    tmdb_ids: list[int] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        try:
            tid = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        tmdb_ids.append(tid)
        if len(tmdb_ids) >= limit * 3:
            break
    if not tmdb_ids:
        return []
    rows = (
        _published_movies(db)
        .filter(Movie.tmdb_id.in_(tmdb_ids), Movie.id != movie.id)
        .all()
    )
    by_tmdb = {int(r.tmdb_id): r for r in rows if r.tmdb_id is not None}
    ordered: list[Movie] = []
    for tid in tmdb_ids:
        row = by_tmdb.get(tid)
        if row is None or row.id in exclude:
            continue
        ordered.append(row)
        if len(ordered) >= limit:
            break
    return ordered


def _from_popular(db: Session, movie: Movie, *, limit: int, exclude: set[int]) -> list[Movie]:
    q = _published_movies(db).filter(Movie.id != movie.id)
    if exclude:
        q = q.filter(Movie.id.notin_(exclude))
    return list(q.order_by(Movie.views.desc(), Movie.id.desc()).limit(limit).all())


def list_similar_movies(
    db: Session,
    movie: Movie,
    *,
    limit: int = 12,
    settings: Settings | None = None,
    client: TMDBClient | None = None,
) -> list[MovieOut]:
    """Priority: same collection → same genres → TMDB similar ∩ catalog → popular."""
    settings = settings or get_settings()
    limit = max(1, min(int(limit), 24))
    picked: list[Movie] = []
    seen: set[int] = {movie.id}

    for batch in (
        _from_collections(db, movie, limit=limit, exclude=seen),
        _from_genres(db, movie, limit=limit, exclude=seen),
        _from_tmdb_similar(db, movie, settings=settings, limit=limit, exclude=seen, client=client),
        _from_popular(db, movie, limit=limit, exclude=seen),
    ):
        for row in batch:
            if row.id in seen:
                continue
            seen.add(row.id)
            picked.append(row)
            if len(picked) >= limit:
                break
        if len(picked) >= limit:
            break

    out: list[MovieOut] = []
    for row in picked[:limit]:
        item = movie_out(row, db)
        # Prefer playable titles in the shelf ordering already established;
        # still include published-but-unplayable so the shelf isn't empty.
        out.append(item)
    return out


def similar_status(db: Session, movie: Movie) -> dict[str, int | bool]:
    settings = get_settings()
    items = list_similar_movies(db, movie, limit=12, settings=settings)
    playable = 0
    for item in items:
        if item.playable or item.has_playable_package:
            playable += 1
    return {
        "similar_count": len(items),
        "playable_similar_count": playable,
        "has_tmdb": bool(movie.tmdb_id),
        "has_trailer": bool((movie.trailer_provider or "").lower() == "youtube" and movie.trailer_key),
    }
