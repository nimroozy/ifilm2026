"""Curated collections service (Collections V1)."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.collections import COLLECTION_TYPES, Collection, CollectionItem, utcnow
from app.models.content import Genre, Movie, Series
from app.schemas.collections import (
    CollectionCreate,
    CollectionItemAdd,
    CollectionItemOut,
    CollectionOut,
    CollectionPublicOut,
    CollectionReorder,
    CollectionUpdate,
)
from app.services.catalog import movie_out, series_out
from app.services.publishing.visibility import apply_public_visibility
from app.utils.slug import slug_or_from_title

logger = logging.getLogger("app.catalog.audit")

COLLECTION_SEED_VERSION = "collections-v1"
MIN_SEED_ITEMS = 3
HOMEPAGE_MIN_VISIBLE_ITEMS = 3


def ensure_unique_collection_slug(
    db: Session, slug: str, *, exclude_id: int | None = None
) -> None:
    q = db.query(Collection).filter(Collection.slug == slug, Collection.deleted_at.is_(None))
    if exclude_id is not None:
        q = q.filter(Collection.id != exclude_id)
    if q.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Collection slug already exists"
        )


def make_collection_slug(
    db: Session,
    title: str,
    slug: str | None,
    *,
    exclude_id: int | None = None,
) -> str:
    try:
        candidate = slug_or_from_title(slug, title)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    ensure_unique_collection_slug(db, candidate, exclude_id=exclude_id)
    return candidate


def get_collection(
    db: Session,
    collection_id: int,
    *,
    include_deleted: bool = False,
) -> Collection:
    q = (
        db.query(Collection)
        .options(
            selectinload(Collection.items).joinedload(CollectionItem.movie).joinedload(Movie.genre_links),
            selectinload(Collection.items).joinedload(CollectionItem.series).joinedload(Series.genre_links),
        )
        .filter(Collection.id == collection_id)
    )
    if not include_deleted:
        q = q.filter(Collection.deleted_at.is_(None))
    collection = q.first()
    if not collection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return collection


def get_collection_by_slug(db: Session, slug: str) -> Collection | None:
    return (
        db.query(Collection)
        .options(
            selectinload(Collection.items).joinedload(CollectionItem.movie).joinedload(Movie.genre_links),
            selectinload(Collection.items).joinedload(CollectionItem.series).joinedload(Series.genre_links),
        )
        .filter(Collection.slug == slug, Collection.deleted_at.is_(None))
        .first()
    )


def _is_content_publicly_visible(movie: Movie | None, series: Series | None) -> bool:
    if movie is not None:
        return movie.deleted_at is None and movie.status == "published"
    if series is not None:
        return series.deleted_at is None and series.status == "published"
    return False


def _check_optimistic(collection: Collection, expected: datetime | None) -> None:
    if expected is None:
        return
    current = collection.updated_at
    if current is None:
        return
    # Normalize naive/aware comparison for SQLite test DB
    if current.tzinfo is None and expected.tzinfo is not None:
        expected = expected.replace(tzinfo=None)
    elif current.tzinfo is not None and expected.tzinfo is None:
        current = current.replace(tzinfo=None)
    if current != expected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Collection was modified concurrently; refresh and retry",
        )


def item_out(
    item: CollectionItem,
    db: Session,
    *,
    public_only: bool = False,
) -> CollectionItemOut | None:
    movie = item.movie
    series = item.series
    visible = _is_content_publicly_visible(movie, series)
    if public_only and not visible:
        return None
    content_type: str
    movie_payload = None
    series_payload = None
    if item.movie_id is not None:
        content_type = "movie"
        if movie is not None:
            movie_payload = movie_out(movie, db)
    else:
        content_type = "series"
        if series is not None:
            series_payload = series_out(series, public_counts=public_only, db=db)
    return CollectionItemOut(
        id=item.id,
        collection_id=item.collection_id,
        movie_id=item.movie_id,
        series_id=item.series_id,
        position=item.position,
        custom_title=item.custom_title,
        custom_description=item.custom_description,
        content_type=content_type,  # type: ignore[arg-type]
        movie=movie_payload,
        series=series_payload,
        created_at=item.created_at,
        publicly_visible=visible,
    )


def visible_item_count(db: Session, collection_id: int) -> int:
    movie_count = (
        db.query(func.count(CollectionItem.id))
        .join(Movie, CollectionItem.movie_id == Movie.id)
        .filter(
            CollectionItem.collection_id == collection_id,
            Movie.deleted_at.is_(None),
            Movie.status == "published",
        )
        .scalar()
        or 0
    )
    series_count = (
        db.query(func.count(CollectionItem.id))
        .join(Series, CollectionItem.series_id == Series.id)
        .filter(
            CollectionItem.collection_id == collection_id,
            Series.deleted_at.is_(None),
            Series.status == "published",
        )
        .scalar()
        or 0
    )
    return int(movie_count) + int(series_count)


def total_item_count(db: Session, collection_id: int) -> int:
    return (
        db.query(func.count(CollectionItem.id))
        .filter(CollectionItem.collection_id == collection_id)
        .scalar()
        or 0
    )


def collection_admin_out(
    collection: Collection,
    db: Session,
    *,
    include_items: bool = True,
) -> CollectionOut:
    items_out: list[CollectionItemOut] = []
    if include_items:
        for item in sorted(collection.items or [], key=lambda i: (i.position, i.id)):
            payload = item_out(item, db, public_only=False)
            if payload is not None:
                items_out.append(payload)
    return CollectionOut(
        id=collection.id,
        title=collection.title,
        slug=collection.slug,
        description=collection.description or "",
        short_description=collection.short_description or "",
        collection_type=collection.collection_type,
        status=collection.status,
        visibility=collection.visibility,
        poster_url=collection.poster_url or "",
        backdrop_url=collection.backdrop_url or "",
        sort_order=collection.sort_order,
        is_featured=bool(collection.is_featured),
        demo_owned=bool(collection.demo_owned),
        demo_seed_version=collection.demo_seed_version or "",
        item_count=total_item_count(db, collection.id),
        visible_item_count=visible_item_count(db, collection.id),
        items=items_out,
        created_by_admin_id=collection.created_by_admin_id,
        updated_by_admin_id=collection.updated_by_admin_id,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
        published_at=collection.published_at,
        archived_at=collection.archived_at,
    )


def collection_public_out(
    collection: Collection,
    db: Session,
    *,
    include_items: bool = True,
) -> CollectionPublicOut:
    items_out: list[CollectionItemOut] = []
    if include_items:
        for item in sorted(collection.items or [], key=lambda i: (i.position, i.id)):
            payload = item_out(item, db, public_only=True)
            if payload is not None:
                items_out.append(payload)
    count = len(items_out) if include_items else visible_item_count(db, collection.id)
    return CollectionPublicOut(
        id=collection.id,
        title=collection.title,
        slug=collection.slug,
        description=collection.description or "",
        short_description=collection.short_description or "",
        collection_type=collection.collection_type,
        poster_url=collection.poster_url or "",
        backdrop_url=collection.backdrop_url or "",
        sort_order=collection.sort_order,
        is_featured=bool(collection.is_featured),
        item_count=count,
        items=items_out if include_items else [],
        published_at=collection.published_at,
    )


def create_collection(
    db: Session,
    payload: CollectionCreate,
    *,
    admin_id: int | None,
) -> Collection:
    slug = make_collection_slug(db, payload.title, payload.slug)
    now = utcnow()
    collection = Collection(
        title=payload.title,
        slug=slug,
        description=payload.description or "",
        short_description=payload.short_description or "",
        collection_type=payload.collection_type,
        status="draft",
        visibility=payload.visibility,
        poster_url=payload.poster_url or "",
        backdrop_url=payload.backdrop_url or "",
        sort_order=payload.sort_order,
        is_featured=payload.is_featured,
        created_by_admin_id=admin_id,
        updated_by_admin_id=admin_id,
        created_at=now,
        updated_at=now,
    )
    db.add(collection)
    db.commit()
    logger.info(
        "catalog_audit event=collection_created details=%s",
        {
            "collection_id": collection.id,
            "slug": collection.slug,
            "status": collection.status,
            "admin_id": admin_id,
        },
    )
    return get_collection(db, collection.id)


def update_collection(
    db: Session,
    collection: Collection,
    payload: CollectionUpdate,
    *,
    admin_id: int | None,
) -> Collection:
    _check_optimistic(collection, payload.expected_updated_at)
    data = payload.model_dump(exclude_unset=True, exclude={"slug", "expected_updated_at"})
    if "title" in payload.model_fields_set or "slug" in payload.model_fields_set:
        title = payload.title if payload.title is not None else collection.title
        slug_value = payload.slug if "slug" in payload.model_fields_set else collection.slug
        collection.slug = make_collection_slug(db, title, slug_value, exclude_id=collection.id)
        if payload.title is not None:
            collection.title = payload.title
    for key, value in data.items():
        if key == "title":
            continue
        setattr(collection, key, value)
    collection.updated_by_admin_id = admin_id
    collection.updated_at = utcnow()
    db.add(collection)
    db.commit()
    logger.info(
        "catalog_audit event=collection_updated details=%s",
        {"collection_id": collection.id, "admin_id": admin_id, "slug": collection.slug},
    )
    return get_collection(db, collection.id)


def publish_collection(
    db: Session, collection: Collection, *, admin_id: int | None, expected_updated_at: datetime | None = None
) -> Collection:
    _check_optimistic(collection, expected_updated_at)
    if collection.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Archived collections cannot be published; restore to draft first",
        )
    now = utcnow()
    collection.status = "published"
    collection.published_at = collection.published_at or now
    collection.archived_at = None
    collection.updated_by_admin_id = admin_id
    collection.updated_at = now
    db.add(collection)
    db.commit()
    logger.info(
        "catalog_audit event=collection_published details=%s",
        {"collection_id": collection.id, "admin_id": admin_id},
    )
    return get_collection(db, collection.id)


def unpublish_collection(
    db: Session, collection: Collection, *, admin_id: int | None, expected_updated_at: datetime | None = None
) -> Collection:
    _check_optimistic(collection, expected_updated_at)
    collection.status = "draft"
    collection.updated_by_admin_id = admin_id
    collection.updated_at = utcnow()
    db.add(collection)
    db.commit()
    logger.info(
        "catalog_audit event=collection_unpublished details=%s",
        {"collection_id": collection.id, "admin_id": admin_id},
    )
    return get_collection(db, collection.id)


def archive_collection(
    db: Session, collection: Collection, *, admin_id: int | None, expected_updated_at: datetime | None = None
) -> Collection:
    _check_optimistic(collection, expected_updated_at)
    now = utcnow()
    collection.status = "archived"
    collection.archived_at = now
    collection.updated_by_admin_id = admin_id
    collection.updated_at = now
    db.add(collection)
    db.commit()
    logger.info(
        "catalog_audit event=collection_archived details=%s",
        {"collection_id": collection.id, "admin_id": admin_id},
    )
    return get_collection(db, collection.id)


def soft_delete_collection(
    db: Session, collection: Collection, *, admin_id: int | None
) -> None:
    """Soft-delete collection. Never deletes movies/series."""
    now = utcnow()
    collection.deleted_at = now
    collection.status = "archived"
    collection.archived_at = collection.archived_at or now
    collection.updated_by_admin_id = admin_id
    collection.updated_at = now
    db.add(collection)
    db.commit()
    logger.info(
        "catalog_audit event=collection_deleted details=%s",
        {"collection_id": collection.id, "admin_id": admin_id},
    )


def _next_position(db: Session, collection_id: int) -> int:
    current = (
        db.query(func.max(CollectionItem.position))
        .filter(CollectionItem.collection_id == collection_id)
        .scalar()
    )
    return 0 if current is None else int(current) + 1


def add_item(
    db: Session,
    collection: Collection,
    payload: CollectionItemAdd,
    *,
    admin_id: int | None,
) -> CollectionItem:
    movie: Movie | None = None
    series: Series | None = None
    if payload.movie_id is not None:
        movie = db.get(Movie, payload.movie_id)
        if movie is None or movie.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Movie not found"
            )
        existing = (
            db.query(CollectionItem)
            .filter(
                CollectionItem.collection_id == collection.id,
                CollectionItem.movie_id == payload.movie_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Movie already in collection"
            )
    else:
        series = db.get(Series, payload.series_id)
        if series is None or series.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Series not found"
            )
        existing = (
            db.query(CollectionItem)
            .filter(
                CollectionItem.collection_id == collection.id,
                CollectionItem.series_id == payload.series_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Series already in collection"
            )

    position = payload.position if payload.position is not None else _next_position(db, collection.id)
    clash = (
        db.query(CollectionItem)
        .filter(CollectionItem.collection_id == collection.id, CollectionItem.position == position)
        .first()
    )
    if clash:
        # Shift subsequent items down
        for row in (
            db.query(CollectionItem)
            .filter(CollectionItem.collection_id == collection.id, CollectionItem.position >= position)
            .order_by(CollectionItem.position.desc())
            .all()
        ):
            row.position += 1
            db.add(row)
        db.flush()

    item = CollectionItem(
        collection_id=collection.id,
        movie_id=payload.movie_id,
        series_id=payload.series_id,
        position=position,
        custom_title=payload.custom_title,
        custom_description=payload.custom_description,
        added_by_admin_id=admin_id,
        created_at=utcnow(),
    )
    db.add(item)
    collection.updated_by_admin_id = admin_id
    collection.updated_at = utcnow()
    db.add(collection)
    db.commit()
    logger.info(
        "catalog_audit event=collection_item_added details=%s",
        {
            "collection_id": collection.id,
            "item_id": item.id,
            "movie_id": item.movie_id,
            "series_id": item.series_id,
            "admin_id": admin_id,
        },
    )
    return item


def remove_item(
    db: Session,
    collection: Collection,
    item_id: int,
    *,
    admin_id: int | None,
) -> None:
    item = (
        db.query(CollectionItem)
        .filter(CollectionItem.id == item_id, CollectionItem.collection_id == collection.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")
    removed_pos = item.position
    db.delete(item)
    db.flush()
    for row in (
        db.query(CollectionItem)
        .filter(CollectionItem.collection_id == collection.id, CollectionItem.position > removed_pos)
        .order_by(CollectionItem.position.asc())
        .all()
    ):
        row.position -= 1
        db.add(row)
    collection.updated_by_admin_id = admin_id
    collection.updated_at = utcnow()
    db.add(collection)
    db.commit()
    logger.info(
        "catalog_audit event=collection_item_removed details=%s",
        {"collection_id": collection.id, "item_id": item_id, "admin_id": admin_id},
    )


def reorder_items(
    db: Session,
    collection: Collection,
    payload: CollectionReorder,
    *,
    admin_id: int | None,
) -> Collection:
    _check_optimistic(collection, payload.expected_updated_at)
    items = (
        db.query(CollectionItem)
        .filter(CollectionItem.collection_id == collection.id)
        .order_by(CollectionItem.position.asc(), CollectionItem.id.asc())
        .all()
    )
    by_id = {item.id: item for item in items}
    if set(payload.item_ids) != set(by_id.keys()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="item_ids must include every collection item exactly once",
        )
    if len(payload.item_ids) != len(set(payload.item_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="item_ids must not contain duplicates",
        )

    # Two-phase update to satisfy unique (collection_id, position).
    for index, item_id in enumerate(payload.item_ids):
        by_id[item_id].position = -(index + 1)
        db.add(by_id[item_id])
    db.flush()
    for index, item_id in enumerate(payload.item_ids):
        by_id[item_id].position = index
        db.add(by_id[item_id])
    collection.updated_by_admin_id = admin_id
    collection.updated_at = utcnow()
    db.add(collection)
    db.commit()
    logger.info(
        "catalog_audit event=collection_items_reordered details=%s",
        {"collection_id": collection.id, "admin_id": admin_id, "count": len(payload.item_ids)},
    )
    return get_collection(db, collection.id)


def list_admin_collections(
    db: Session,
    *,
    q: str | None = None,
    status_filter: str | None = None,
    collection_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Collection], int]:
    query = db.query(Collection).filter(Collection.deleted_at.is_(None))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Collection.title.ilike(like), Collection.slug.ilike(like)))
    if status_filter:
        query = query.filter(Collection.status == status_filter)
    if collection_type:
        if collection_type not in COLLECTION_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"collection_type must be one of {COLLECTION_TYPES}",
            )
        query = query.filter(Collection.collection_type == collection_type)
    query = query.order_by(Collection.sort_order.asc(), Collection.id.asc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def _public_collections_base(db: Session):
    return (
        db.query(Collection)
        .filter(
            Collection.deleted_at.is_(None),
            Collection.status == "published",
            Collection.visibility == "public",
        )
    )


def list_public_collections(
    db: Session,
    *,
    collection_type: str | None = None,
    featured_only: bool = False,
    page: int = 1,
    page_size: int = 20,
    include_items: bool = False,
    min_visible_items: int = 1,
) -> tuple[list[Collection], int]:
    """Return published collections that have at least one publicly visible item."""
    query = _public_collections_base(db)
    if featured_only:
        query = query.filter(Collection.is_featured.is_(True))
    if collection_type:
        if collection_type not in COLLECTION_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"collection_type must be one of {COLLECTION_TYPES}",
            )
        query = query.filter(Collection.collection_type == collection_type)

    # Filter empty collections via EXISTS on published movie/series items.
    movie_exists = (
        db.query(CollectionItem.id)
        .join(Movie, CollectionItem.movie_id == Movie.id)
        .filter(
            CollectionItem.collection_id == Collection.id,
            Movie.deleted_at.is_(None),
            Movie.status == "published",
        )
        .exists()
    )
    series_exists = (
        db.query(CollectionItem.id)
        .join(Series, CollectionItem.series_id == Series.id)
        .filter(
            CollectionItem.collection_id == Collection.id,
            Series.deleted_at.is_(None),
            Series.status == "published",
        )
        .exists()
    )
    query = query.filter(or_(movie_exists, series_exists))
    query = query.order_by(Collection.sort_order.asc(), Collection.id.asc())

    # Materialize then filter by min_visible when > 1 (homepage shelf).
    all_rows = query.all()
    if min_visible_items > 1:
        filtered: list[Collection] = []
        for row in all_rows:
            if visible_item_count(db, row.id) >= min_visible_items:
                filtered.append(row)
        all_rows = filtered

    total = len(all_rows)
    page_rows = all_rows[(page - 1) * page_size : page * page_size]

    if include_items and page_rows:
        ids = [c.id for c in page_rows]
        loaded = (
            db.query(Collection)
            .options(
                selectinload(Collection.items)
                .joinedload(CollectionItem.movie)
                .joinedload(Movie.genre_links),
                selectinload(Collection.items)
                .joinedload(CollectionItem.series)
                .joinedload(Series.genre_links),
            )
            .filter(Collection.id.in_(ids))
            .all()
        )
        by_id = {c.id: c for c in loaded}
        page_rows = [by_id[i] for i in ids if i in by_id]

    return page_rows, total


def get_public_collection_by_slug(db: Session, slug: str) -> Collection:
    collection = get_collection_by_slug(db, slug)
    if (
        collection is None
        or collection.status != "published"
        or collection.visibility != "public"
        or collection.deleted_at is not None
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    if visible_item_count(db, collection.id) < 1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return collection


def search_picker_content(
    db: Session,
    *,
    q: str | None = None,
    content_type: str | None = None,
    published_only: bool = False,
    year: int | None = None,
    genre: str | None = None,
    language: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Admin item picker search across movies and series."""
    movies: list[Movie] = []
    series_rows: list[Series] = []
    if content_type in (None, "movie", ""):
        mq = db.query(Movie).options(joinedload(Movie.genre_links)).filter(Movie.deleted_at.is_(None))
        if published_only:
            mq = apply_public_visibility(mq, Movie)
        if q:
            like = f"%{q}%"
            mq = mq.filter(or_(Movie.title.ilike(like), Movie.slug.ilike(like)))
        if year is not None:
            mq = mq.filter(Movie.release_year == year)
        if language:
            mq = mq.filter(Movie.language.ilike(f"%{language}%"))
        if genre:
            mq = mq.filter(Movie.genre_links.any(Genre.name.ilike(genre)))
        movies = mq.order_by(Movie.title.asc()).limit(page_size).all()
    if content_type in (None, "series", ""):
        sq = db.query(Series).options(joinedload(Series.genre_links)).filter(Series.deleted_at.is_(None))
        if published_only:
            sq = apply_public_visibility(sq, Series)
        if q:
            like = f"%{q}%"
            sq = sq.filter(or_(Series.title.ilike(like), Series.slug.ilike(like)))
        if year is not None:
            sq = sq.filter(Series.release_year == year)
        if language:
            sq = sq.filter(Series.language.ilike(f"%{language}%"))
        if genre:
            sq = sq.filter(Series.genre_links.any(Genre.name.ilike(genre)))
        series_rows = sq.order_by(Series.title.asc()).limit(page_size).all()
    return {
        "movies": [movie_out(m, db) for m in movies],
        "series": [series_out(s, db=db) for s in series_rows],
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# Demo seed (idempotent)
# ---------------------------------------------------------------------------

SEED_COLLECTION_SPECS: tuple[dict, ...] = (
    {
        "title": "Popular Movies",
        "slug": "popular-movies",
        "description": "Audience favorites from the current catalog.",
        "short_description": "Popular titles to start with.",
        "collection_type": "editorial",
        "is_featured": True,
        "sort_order": 10,
        "match": "popular",
    },
    {
        "title": "Family & Animation",
        "slug": "family-animation",
        "description": "Family-friendly and animated titles.",
        "short_description": "Watch together.",
        "collection_type": "genre_feature",
        "is_featured": True,
        "sort_order": 20,
        "match": "family",
    },
    {
        "title": "Action Picks",
        "slug": "action-picks",
        "description": "High-energy action selections.",
        "short_description": "Action highlights.",
        "collection_type": "genre_feature",
        "is_featured": True,
        "sort_order": 30,
        "match": "action",
    },
    {
        "title": "Science Fiction",
        "slug": "science-fiction",
        "description": "Science fiction from the catalog.",
        "short_description": "Sci-fi picks.",
        "collection_type": "genre_feature",
        "is_featured": False,
        "sort_order": 40,
        "match": "scifi",
    },
    {
        "title": "Classic Cinema",
        "slug": "classic-cinema",
        "description": "Older and classic titles from the catalog.",
        "short_description": "Classic films.",
        "collection_type": "editorial",
        "is_featured": False,
        "sort_order": 50,
        "match": "classic",
    },
)


def _match_movies(db: Session, match: str) -> list[Movie]:
    base = apply_public_visibility(db.query(Movie).filter(Movie.deleted_at.is_(None)), Movie)
    if match == "popular":
        return (
            base.order_by(Movie.is_trending.desc(), Movie.is_featured.desc(), Movie.id.asc())
            .limit(24)
            .all()
        )
    if match == "family":
        return (
            base.filter(
                or_(
                    Movie.genre_links.any(Genre.name.ilike("Animation")),
                    Movie.genre_links.any(Genre.name.ilike("Family")),
                    Movie.genre_links.any(Genre.name.ilike("Children")),
                )
            )
            .order_by(Movie.id.asc())
            .limit(24)
            .all()
        )
    if match == "action":
        return (
            base.filter(Movie.genre_links.any(Genre.name.ilike("Action")))
            .order_by(Movie.id.asc())
            .limit(24)
            .all()
        )
    if match == "scifi":
        return (
            base.filter(
                or_(
                    Movie.genre_links.any(Genre.name.ilike("Science Fiction")),
                    Movie.genre_links.any(Genre.name.ilike("Sci-Fi")),
                    Movie.genre_links.any(Genre.name.ilike("Sci Fi")),
                )
            )
            .order_by(Movie.id.asc())
            .limit(24)
            .all()
        )
    if match == "classic":
        return (
            base.filter(Movie.release_year.isnot(None), Movie.release_year <= 2000)
            .order_by(Movie.release_year.asc(), Movie.id.asc())
            .limit(24)
            .all()
        )
    return []


def seed_demo_collections(
    db: Session,
    *,
    admin_id: int | None = None,
    min_items: int = MIN_SEED_ITEMS,
) -> dict:
    """Idempotent seed of demo collections from real published catalog items.

    Never deletes or overwrites manually created (non-demo) collections.
    """
    created = 0
    updated = 0
    skipped = 0
    collection_ids: list[int] = []

    for spec in SEED_COLLECTION_SPECS:
        movies = _match_movies(db, spec["match"])
        if len(movies) < min_items:
            skipped += 1
            continue

        existing = (
            db.query(Collection)
            .filter(Collection.slug == spec["slug"], Collection.deleted_at.is_(None))
            .first()
        )
        if existing and not existing.demo_owned:
            # Preserve manually curated collection with same slug.
            skipped += 1
            continue

        now = utcnow()
        if existing is None:
            collection = Collection(
                title=spec["title"],
                slug=spec["slug"],
                description=spec["description"],
                short_description=spec["short_description"],
                collection_type=spec["collection_type"],
                status="published",
                visibility="public",
                sort_order=spec["sort_order"],
                is_featured=spec["is_featured"],
                demo_owned=True,
                demo_seed_version=COLLECTION_SEED_VERSION,
                created_by_admin_id=admin_id,
                updated_by_admin_id=admin_id,
                created_at=now,
                updated_at=now,
                published_at=now,
            )
            db.add(collection)
            db.flush()
            created += 1
        else:
            collection = existing
            collection.title = spec["title"]
            collection.description = spec["description"]
            collection.short_description = spec["short_description"]
            collection.collection_type = spec["collection_type"]
            collection.status = "published"
            collection.visibility = "public"
            collection.sort_order = spec["sort_order"]
            collection.is_featured = spec["is_featured"]
            collection.demo_owned = True
            collection.demo_seed_version = COLLECTION_SEED_VERSION
            collection.updated_by_admin_id = admin_id
            collection.updated_at = now
            collection.published_at = collection.published_at or now
            # Clear existing demo items then re-add (idempotent membership).
            db.query(CollectionItem).filter(CollectionItem.collection_id == collection.id).delete(
                synchronize_session=False
            )
            db.flush()
            updated += 1

        for index, movie in enumerate(movies):
            db.add(
                CollectionItem(
                    collection_id=collection.id,
                    movie_id=movie.id,
                    series_id=None,
                    position=index,
                    added_by_admin_id=admin_id,
                    created_at=now,
                )
            )
        collection_ids.append(collection.id)

    db.commit()
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "collection_ids": collection_ids,
        "seed_version": COLLECTION_SEED_VERSION,
    }
