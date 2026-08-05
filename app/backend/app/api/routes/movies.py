from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import joinedload

from app.core.deps import DbSession, require_permissions
from app.models.admin import AdminUser
from app.models.content import Movie
from app.models.enums import SORT_OPTIONS
from app.schemas.common import Envelope, Message, paginated
from app.schemas.content import MovieCreate, MovieOut, MovieUpdate, PublishAction
from app.services.catalog import (
    apply_sort,
    ensure_unique_imdb,
    filter_catalog_query,
    get_movie,
    load_genres,
    make_slug_for_movie,
    movie_out,
    resolve_movie,
    soft_delete,
    utcnow,
)
from app.services.publishing import workflow as publishing_workflow

router = APIRouter(tags=["movies"])

SortParam = Annotated[str, Query(description="Sort order")]


def _list_query(
    db: DbSession,
    *,
    q: str | None,
    genre: str | None,
    year: int | None,
    language: str | None,
    featured: bool | None,
    trending: bool | None,
    status_filter: str | None,
    published_only: bool,
    sort: str,
):
    query = db.query(Movie).options(joinedload(Movie.genre_links))
    query = filter_catalog_query(
        query,
        Movie,
        q=q,
        genre=genre,
        year=year,
        language=language,
        featured=featured,
        trending=trending,
        status=status_filter,
        published_only=published_only,
    )
    return apply_sort(query, Movie, sort if sort in SORT_OPTIONS else "newest")


@router.get("/movies", response_model=Envelope[MovieOut])
def list_movies(
    db: DbSession,
    q: str | None = None,
    genre: str | None = None,
    year: int | None = None,
    language: str | None = None,
    featured: bool | None = None,
    trending: bool | None = None,
    sort: SortParam = "newest",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Envelope[MovieOut]:
    query = _list_query(
        db,
        q=q,
        genre=genre,
        year=year,
        language=language,
        featured=featured,
        trending=trending,
        status_filter=None,
        published_only=True,
        sort=sort,
    )
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return paginated([movie_out(m, db) for m in items], total=total, page=page, page_size=page_size)


@router.get("/movies/{id_or_slug}", response_model=MovieOut)
def get_public_movie(id_or_slug: str, db: DbSession) -> MovieOut:
    return movie_out(resolve_movie(db, id_or_slug, published_only=True), db)


@router.get("/admin/movies", response_model=Envelope[MovieOut])
def admin_list_movies(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("movies.read"))],
    q: str | None = None,
    genre: str | None = None,
    year: int | None = None,
    language: str | None = None,
    featured: bool | None = None,
    trending: bool | None = None,
    status: str | None = None,
    sort: SortParam = "newest",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Envelope[MovieOut]:
    query = _list_query(
        db,
        q=q,
        genre=genre,
        year=year,
        language=language,
        featured=featured,
        trending=trending,
        status_filter=status,
        published_only=False,
        sort=sort,
    )
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return paginated([movie_out(m, db) for m in items], total=total, page=page, page_size=page_size)


@router.post("/admin/movies", response_model=MovieOut, status_code=status.HTTP_201_CREATED)
def create_movie(
    payload: MovieCreate,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("movies.manage"))],
) -> MovieOut:
    import logging

    data = payload.model_dump(exclude={"genre_ids", "slug"})
    data["status"] = "draft"
    slug = make_slug_for_movie(db, payload.title, payload.slug)
    ensure_unique_imdb(db, Movie, payload.imdb_id)
    genres = load_genres(db, payload.genre_ids)
    movie = Movie(**data, slug=slug)
    movie.genre_links = genres
    db.add(movie)
    db.commit()
    logging.getLogger("app.catalog.audit").info(
        "catalog_audit event=movie_created details=%s",
        {
            "movie_id": movie.id,
            "slug": movie.slug,
            "status": movie.status,
            "admin_id": admin.id,
            "tmdb_id": getattr(movie, "tmdb_id", None),
        },
    )
    return movie_out(get_movie(db, movie.id), db)


@router.get("/admin/movies/{movie_id}", response_model=MovieOut)
def admin_get_movie(
    movie_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("movies.read"))],
) -> MovieOut:
    return movie_out(get_movie(db, movie_id), db)


@router.patch("/admin/movies/{movie_id}", response_model=MovieOut)
def update_movie(
    movie_id: int,
    payload: MovieUpdate,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("movies.manage"))],
) -> MovieOut:
    movie = get_movie(db, movie_id)
    data = payload.model_dump(exclude_unset=True, exclude={"genre_ids", "slug"})
    if "title" in payload.model_fields_set or "slug" in payload.model_fields_set:
        title = payload.title if payload.title is not None else movie.title
        slug_value = payload.slug if "slug" in payload.model_fields_set else movie.slug
        movie.slug = make_slug_for_movie(db, title, slug_value, exclude_id=movie.id)
    if "imdb_id" in payload.model_fields_set:
        ensure_unique_imdb(db, Movie, payload.imdb_id, exclude_id=movie.id)
    for key, value in data.items():
        setattr(movie, key, value)
    if "genre_ids" in payload.model_fields_set and payload.genre_ids is not None:
        movie.genre_links = load_genres(db, payload.genre_ids)
    # status is owned by publishing workflow — ignore if present on legacy clients
    movie.updated_at = utcnow()
    db.add(movie)
    db.commit()
    return movie_out(get_movie(db, movie.id), db)


@router.delete("/admin/movies/{movie_id}", response_model=Message)
def delete_movie(
    movie_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("movies.manage"))],
) -> Message:
    movie = get_movie(db, movie_id)
    soft_delete(movie)
    movie.updated_at = utcnow()
    db.add(movie)
    db.commit()
    return Message(detail="Movie deleted")


@router.post("/admin/movies/{movie_id}/publish", response_model=PublishAction)
def publish_movie(
    movie_id: int,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("catalog.publish"))],
) -> PublishAction:
    """Legacy alias — prefer POST /api/admin/catalog/movie/{id}/publish."""
    movie = publishing_workflow.workflow_http(
        publishing_workflow.publish, db, entity_type="movie", entity_id=movie_id, actor=admin
    )
    db.commit()
    return PublishAction(detail="ok", status=movie.status)


@router.post("/admin/movies/{movie_id}/unpublish", response_model=PublishAction)
def unpublish_movie(
    movie_id: int,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("catalog.publish"))],
) -> PublishAction:
    """Legacy alias — prefer POST /api/admin/catalog/movie/{id}/unpublish."""
    movie = publishing_workflow.workflow_http(
        publishing_workflow.unpublish, db, entity_type="movie", entity_id=movie_id, actor=admin
    )
    db.commit()
    return PublishAction(detail="ok", status=movie.status)
