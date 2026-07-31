from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy.orm import joinedload

from app.core.deps import DbSession
from app.models.content import Movie, Series
from app.schemas.content import MovieOut, SeriesOut
from app.services.catalog import movie_out, not_deleted, series_out

router = APIRouter(tags=["search"])


@router.get("/search")
def search(db: DbSession, q: str = Query("", min_length=0)) -> dict[str, list[MovieOut] | list[SeriesOut]]:
    if not q.strip():
        return {"movies": [], "series": []}
    like = f"%{q.strip()}%"
    movies = (
        not_deleted(db.query(Movie), Movie)
        .options(joinedload(Movie.genre_links))
        .filter(Movie.status == "published")
        .filter(
            Movie.title.ilike(like)
            | Movie.original_title.ilike(like)
            | Movie.director.ilike(like)
            | Movie.slug.ilike(like)
        )
        .order_by(Movie.created_at.desc())
        .limit(20)
        .all()
    )
    series_items = (
        not_deleted(db.query(Series), Series)
        .options(joinedload(Series.genre_links), joinedload(Series.seasons))
        .filter(Series.status == "published")
        .filter(
            Series.title.ilike(like)
            | Series.original_title.ilike(like)
            | Series.slug.ilike(like)
        )
        .order_by(Series.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "movies": [movie_out(m) for m in movies],
        "series": [series_out(s) for s in series_items],
    }
