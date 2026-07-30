from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import joinedload

from app.core.deps import DbSession, require_permissions
from app.models.admin import AdminUser
from app.models.content import Genre
from app.schemas.common import Envelope, Message, paginated
from app.schemas.content import GenreCreate, GenreOut, GenreUpdate
from app.services.catalog import ensure_unique_genre_slug, genre_out, utcnow
from app.utils.slug import slug_or_from_title

router = APIRouter(tags=["genres"])


def _make_genre_slug(
    db: DbSession,
    name: str,
    slug: str | None,
    *,
    exclude_id: int | None = None,
) -> str:
    try:
        candidate = slug_or_from_title(slug, name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    ensure_unique_genre_slug(db, candidate, exclude_id=exclude_id)
    return candidate


def _get_genre(db: DbSession, genre_id: int) -> Genre:
    genre = (
        db.query(Genre)
        .options(joinedload(Genre.movies), joinedload(Genre.series))
        .filter(Genre.id == genre_id)
        .first()
    )
    if not genre:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Genre not found")
    return genre


@router.get("/genres", response_model=Envelope[GenreOut])
def list_genres(
    db: DbSession,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
) -> Envelope[GenreOut]:
    query = db.query(Genre).options(joinedload(Genre.movies), joinedload(Genre.series))
    if q:
        like = f"%{q}%"
        query = query.filter(Genre.name.ilike(like) | Genre.slug.ilike(like))
    query = query.order_by(Genre.name.asc(), Genre.id.asc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return paginated([genre_out(g) for g in items], total=total, page=page, page_size=page_size)


@router.get("/admin/genres", response_model=Envelope[GenreOut])
def admin_list_genres(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("genres.read"))],
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
) -> Envelope[GenreOut]:
    return list_genres(db, q=q, page=page, page_size=page_size)


@router.post("/admin/genres", response_model=GenreOut, status_code=status.HTTP_201_CREATED)
def create_genre(
    payload: GenreCreate,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("genres.manage"))],
) -> GenreOut:
    slug = _make_genre_slug(db, payload.name, payload.slug)
    genre = Genre(
        name=payload.name,
        slug=slug,
        description=payload.description or "",
    )
    db.add(genre)
    db.commit()
    return genre_out(_get_genre(db, genre.id))


@router.get("/admin/genres/{genre_id}", response_model=GenreOut)
def get_genre(
    genre_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("genres.read"))],
) -> GenreOut:
    return genre_out(_get_genre(db, genre_id))


@router.patch("/admin/genres/{genre_id}", response_model=GenreOut)
def update_genre(
    genre_id: int,
    payload: GenreUpdate,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("genres.manage"))],
) -> GenreOut:
    genre = _get_genre(db, genre_id)
    data = payload.model_dump(exclude_unset=True, exclude={"slug"})
    if "name" in payload.model_fields_set or "slug" in payload.model_fields_set:
        name = payload.name if payload.name is not None else genre.name
        slug_value = payload.slug if "slug" in payload.model_fields_set else genre.slug
        genre.slug = _make_genre_slug(db, name, slug_value, exclude_id=genre.id)
    for key, value in data.items():
        setattr(genre, key, value)
    genre.updated_at = utcnow()
    db.add(genre)
    db.commit()
    return genre_out(_get_genre(db, genre.id))


@router.delete("/admin/genres/{genre_id}", response_model=Message)
def delete_genre(
    genre_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("genres.manage"))],
) -> Message:
    genre = _get_genre(db, genre_id)
    active_movies = [m for m in (genre.movies or []) if m.deleted_at is None]
    active_series = [s for s in (genre.series or []) if s.deleted_at is None]
    if active_movies or active_series:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Genre is assigned to one or more movies or series",
        )
    db.delete(genre)
    db.commit()
    return Message(detail="Genre deleted")
