from fastapi import APIRouter, Query

from app.core.deps import DbSession
from app.models.content import Movie, Series
from app.schemas.content import MovieOut, SeriesOut

router = APIRouter(tags=["search"])


@router.get("/search")
def search(db: DbSession, q: str = Query("", min_length=0)):
    if not q.strip():
        return {"movies": [], "series": []}
    like = f"%{q.strip()}%"
    movies = (
        db.query(Movie)
        .filter(Movie.published.is_(True))
        .filter(Movie.title.ilike(like) | Movie.original_title.ilike(like) | Movie.director.ilike(like))
        .limit(20)
        .all()
    )
    series_items = (
        db.query(Series)
        .filter(Series.published.is_(True))
        .filter(Series.title.ilike(like) | Series.original_title.ilike(like))
        .limit(20)
        .all()
    )
    return {
        "movies": [MovieOut.model_validate(m) for m in movies],
        "series": [SeriesOut.from_orm_series(s) for s in series_items],
    }


@router.get("/genres")
def genres():
    return {
        "items": [
            "Action",
            "Comedy",
            "Drama",
            "Thriller",
            "Romance",
            "Horror",
            "Sci-Fi",
            "Documentary",
            "Animation",
            "Family",
            "Adventure",
            "Crime",
            "Fantasy",
            "War",
            "History",
        ]
    }
