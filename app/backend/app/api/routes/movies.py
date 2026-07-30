from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_

from app.core.deps import CurrentAdmin, DbSession
from app.models.content import Movie
from app.schemas.common import Message, Page
from app.schemas.content import MovieCreate, MovieOut, MovieUpdate

router = APIRouter(tags=["movies"])


def _serialize(movie: Movie) -> MovieOut:
    return MovieOut.model_validate(movie)


@router.get("/movies", response_model=Page[MovieOut])
def list_movies(
    db: DbSession,
    q: Optional[str] = None,
    genre: Optional[str] = None,
    sort: str = Query("newest", pattern="^(newest|rating|popular|title)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    published_only: bool = True,
):
    query = db.query(Movie)
    if published_only:
        query = query.filter(Movie.published.is_(True))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Movie.title.ilike(like), Movie.original_title.ilike(like), Movie.director.ilike(like)))
    if genre:
        # JSON contains works on Postgres; for SQLite use cast/like fallback in tests via Python filter if needed.
        try:
            query = query.filter(Movie.genres.contains([genre]))
        except Exception:
            pass
    if sort == "rating":
        query = query.order_by(Movie.rating.desc())
    elif sort == "popular":
        query = query.order_by(Movie.views.desc())
    elif sort == "title":
        query = query.order_by(Movie.title.asc())
    else:
        query = query.order_by(Movie.id.desc())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    if genre:
        items = [m for m in items if genre in (m.genres or [])]
    return Page(items=[_serialize(m) for m in items], total=total, page=page, page_size=page_size)


@router.get("/movies/{movie_id}", response_model=MovieOut)
def get_movie(movie_id: int, db: DbSession):
    movie = db.get(Movie, movie_id)
    if not movie or not movie.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    return _serialize(movie)


@router.post("/admin/movies", response_model=MovieOut, status_code=status.HTTP_201_CREATED)
def create_movie(payload: MovieCreate, db: DbSession, _: CurrentAdmin):
    movie = Movie(**payload.model_dump())
    db.add(movie)
    db.commit()
    db.refresh(movie)
    return _serialize(movie)


@router.patch("/admin/movies/{movie_id}", response_model=MovieOut)
def update_movie(movie_id: int, payload: MovieUpdate, db: DbSession, _: CurrentAdmin):
    movie = db.get(Movie, movie_id)
    if not movie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(movie, key, value)
    db.add(movie)
    db.commit()
    db.refresh(movie)
    return _serialize(movie)


@router.delete("/admin/movies/{movie_id}", response_model=Message)
def delete_movie(movie_id: int, db: DbSession, _: CurrentAdmin):
    movie = db.get(Movie, movie_id)
    if not movie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    db.delete(movie)
    db.commit()
    return Message(detail="Movie deleted")
