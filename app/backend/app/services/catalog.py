"""Catalog domain services: queries, publishing rules, serialization."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.content import Episode, Genre, Movie, Season, Series
from app.models.enums import SORT_OPTIONS
from app.schemas.content import (
    EpisodeOut,
    GenreOut,
    MovieOut,
    SeasonOut,
    SeriesOut,
)
from app.utils.slug import slug_or_from_title


def utcnow() -> datetime:
    return datetime.now(UTC)


def not_deleted(query, model):
    return query.filter(model.deleted_at.is_(None))


def genre_out(genre: Genre, *, movie_count: int | None = None, series_count: int | None = None) -> GenreOut:
    return GenreOut(
        id=genre.id,
        name=genre.name,
        slug=genre.slug,
        description=genre.description or "",
        movie_count=movie_count if movie_count is not None else len([m for m in (genre.movies or []) if m.deleted_at is None]),
        series_count=series_count
        if series_count is not None
        else len([s for s in (genre.series or []) if s.deleted_at is None]),
        created_at=genre.created_at,
        updated_at=genre.updated_at,
    )


def movie_out(movie: Movie) -> MovieOut:
    genres = [genre_out(g, movie_count=0, series_count=0) for g in (movie.genre_links or [])]
    return MovieOut(
        id=movie.id,
        title=movie.title,
        original_title=movie.original_title or "",
        slug=movie.slug,
        description=movie.description or "",
        short_description=movie.short_description or "",
        release_year=movie.release_year,
        release_date=movie.release_date,
        duration_minutes=movie.duration_minutes,
        age_rating=movie.age_rating or "",
        language=movie.language or "",
        country=movie.country or "",
        imdb_id=movie.imdb_id,
        imdb_rating=movie.imdb_rating,
        poster_url=movie.poster_url or "",
        backdrop_url=movie.backdrop_url or "",
        trailer_url=movie.trailer_url or "",
        status=movie.status,
        is_featured=bool(movie.is_featured),
        is_trending=bool(movie.is_trending),
        published_at=movie.published_at,
        created_at=movie.created_at,
        updated_at=movie.updated_at,
        genres=genres,
        director=movie.director or "",
        cast=movie.cast or [],
        audio=movie.audio or [],
        subtitles=movie.subtitles or [],
        qualities=movie.qualities or [],
        dubbed=movie.dubbed or [],
        views=movie.views or 0,
        type="movie",
        hls_path=movie.hls_path,
        year=movie.release_year,
        duration=movie.duration_minutes,
        rating=movie.imdb_rating,
        poster=movie.poster_url or "",
        backdrop=movie.backdrop_url or "",
        featured=bool(movie.is_featured),
    )


def series_out(series: Series) -> SeriesOut:
    genres = [genre_out(g, movie_count=0, series_count=0) for g in (series.genre_links or [])]
    seasons = [s for s in (series.seasons or []) if s.deleted_at is None]
    episode_count = sum(len([e for e in (s.episodes or []) if e.deleted_at is None]) for s in seasons)
    return SeriesOut(
        id=series.id,
        title=series.title,
        original_title=series.original_title or "",
        slug=series.slug,
        description=series.description or "",
        short_description=series.short_description or "",
        release_year=series.release_year,
        end_year=series.end_year,
        age_rating=series.age_rating or "",
        language=series.language or "",
        country=series.country or "",
        imdb_id=series.imdb_id,
        imdb_rating=series.imdb_rating,
        poster_url=series.poster_url or "",
        backdrop_url=series.backdrop_url or "",
        trailer_url=series.trailer_url or "",
        status=series.status,
        airing_status=series.airing_status or "Ongoing",
        is_featured=bool(series.is_featured),
        is_trending=bool(series.is_trending),
        published_at=series.published_at,
        created_at=series.created_at,
        updated_at=series.updated_at,
        genres=genres,
        season_count=len(seasons),
        episode_count=episode_count,
        audio=series.audio or [],
        subtitles=series.subtitles or [],
        dubbed=series.dubbed or [],
        new_episode=bool(series.new_episode),
        views=series.views or 0,
        type="series",
        year=series.release_year,
        seasons=len(seasons),
        episodes=episode_count,
        rating=series.imdb_rating,
        poster=series.poster_url or "",
        backdrop=series.backdrop_url or "",
        featured=bool(series.is_featured),
    )


def season_out(season: Season) -> SeasonOut:
    episodes = [e for e in (season.episodes or []) if e.deleted_at is None]
    return SeasonOut(
        id=season.id,
        series_id=season.series_id,
        season_number=season.season_number,
        title=season.title or "",
        description=season.description or "",
        poster_url=season.poster_url or "",
        release_year=season.release_year,
        status=season.status,
        episode_count=len(episodes),
        created_at=season.created_at,
        updated_at=season.updated_at,
    )


def episode_out(episode: Episode) -> EpisodeOut:
    return EpisodeOut(
        id=episode.id,
        season_id=episode.season_id,
        series_id=episode.series_id,
        episode_number=episode.episode_number,
        title=episode.title,
        description=episode.description or "",
        duration_minutes=episode.duration_minutes,
        release_date=episode.release_date,
        thumbnail_url=episode.thumbnail_url or "",
        status=episode.status,
        published_at=episode.published_at,
        created_at=episode.created_at,
        updated_at=episode.updated_at,
        hls_path=episode.hls_path,
        season=episode.season.season_number if episode.season else None,
        episode=episode.episode_number,
        duration=episode.duration_minutes,
        thumbnail=episode.thumbnail_url or "",
    )


def load_genres(db: Session, genre_ids: list[int]) -> list[Genre]:
    if not genre_ids:
        return []
    genres = db.query(Genre).filter(Genre.id.in_(genre_ids)).all()
    if len(genres) != len(set(genre_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more genres not found")
    return genres


def ensure_unique_movie_slug(db: Session, slug: str, *, exclude_id: int | None = None) -> None:
    q = not_deleted(db.query(Movie), Movie).filter(Movie.slug == slug)
    if exclude_id is not None:
        q = q.filter(Movie.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Movie slug already exists")


def ensure_unique_series_slug(db: Session, slug: str, *, exclude_id: int | None = None) -> None:
    q = not_deleted(db.query(Series), Series).filter(Series.slug == slug)
    if exclude_id is not None:
        q = q.filter(Series.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Series slug already exists")


def ensure_unique_genre_slug(db: Session, slug: str, *, exclude_id: int | None = None) -> None:
    q = db.query(Genre).filter(Genre.slug == slug)
    if exclude_id is not None:
        q = q.filter(Genre.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Genre slug already exists")


def ensure_unique_imdb(db: Session, model, imdb_id: str | None, *, exclude_id: int | None = None) -> None:
    if not imdb_id:
        return
    q = not_deleted(db.query(model), model).filter(model.imdb_id == imdb_id)
    if exclude_id is not None:
        q = q.filter(model.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="IMDb identifier already exists")


def apply_sort(query, model, sort: str):
    if sort not in SORT_OPTIONS:
        sort = "newest"
    rating_col = getattr(model, "imdb_rating", None)
    if sort == "oldest":
        return query.order_by(model.created_at.asc(), model.id.asc())
    if sort == "title_asc":
        return query.order_by(model.title.asc(), model.id.asc())
    if sort == "title_desc":
        return query.order_by(model.title.desc(), model.id.desc())
    if sort == "rating_desc" and rating_col is not None:
        return query.order_by(rating_col.desc(), model.id.desc())
    if sort == "recently_updated":
        return query.order_by(model.updated_at.desc(), model.id.desc())
    return query.order_by(model.created_at.desc(), model.id.desc())


def filter_catalog_query(
    query,
    model,
    *,
    q: str | None = None,
    genre: str | None = None,
    year: int | None = None,
    language: str | None = None,
    featured: bool | None = None,
    trending: bool | None = None,
    status: str | None = None,
    published_only: bool = False,
):
    query = not_deleted(query, model)
    if published_only:
        query = query.filter(model.status == "published")
    elif status:
        query = query.filter(model.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(model.title.ilike(like), model.original_title.ilike(like), model.slug.ilike(like)))
    if year is not None:
        query = query.filter(model.release_year == year)
    if language:
        query = query.filter(model.language.ilike(language))
    if featured is not None:
        query = query.filter(model.is_featured.is_(featured))
    if trending is not None:
        query = query.filter(model.is_trending.is_(trending))
    if genre:
        if model is Movie:
            query = query.join(Movie.genre_links).filter(or_(Genre.slug == genre, Genre.name.ilike(genre)))
        elif model is Series:
            query = query.join(Series.genre_links).filter(or_(Genre.slug == genre, Genre.name.ilike(genre)))
        query = query.distinct()
    return query


def get_movie(db: Session, movie_id: int, *, include_deleted: bool = False) -> Movie:
    movie = (
        db.query(Movie)
        .options(joinedload(Movie.genre_links))
        .filter(Movie.id == movie_id)
        .first()
    )
    if not movie or (movie.deleted_at is not None and not include_deleted):
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie


def get_series(db: Session, series_id: int, *, include_deleted: bool = False) -> Series:
    series = (
        db.query(Series)
        .options(joinedload(Series.genre_links), joinedload(Series.seasons).joinedload(Season.episodes))
        .filter(Series.id == series_id)
        .first()
    )
    if not series or (series.deleted_at is not None and not include_deleted):
        raise HTTPException(status_code=404, detail="Series not found")
    return series


def resolve_movie(db: Session, id_or_slug: str, *, published_only: bool = False) -> Movie:
    query = db.query(Movie).options(joinedload(Movie.genre_links))
    query = not_deleted(query, Movie)
    if id_or_slug.isdigit():
        query = query.filter(Movie.id == int(id_or_slug))
    else:
        query = query.filter(Movie.slug == id_or_slug)
    if published_only:
        query = query.filter(Movie.status == "published")
    movie = query.first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie


def resolve_series(db: Session, id_or_slug: str, *, published_only: bool = False) -> Series:
    query = (
        db.query(Series)
        .options(joinedload(Series.genre_links), joinedload(Series.seasons).joinedload(Season.episodes))
    )
    query = not_deleted(query, Series)
    if id_or_slug.isdigit():
        query = query.filter(Series.id == int(id_or_slug))
    else:
        query = query.filter(Series.slug == id_or_slug)
    if published_only:
        query = query.filter(Series.status == "published")
    series = query.first()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    return series


def soft_delete(entity) -> None:
    entity.deleted_at = utcnow()
    entity.status = "archived"


def publish_entity(entity) -> None:
    entity.status = "published"
    entity.published_at = entity.published_at or utcnow()


def unpublish_entity(entity) -> None:
    entity.status = "draft"


def publish_episode(db: Session, episode: Episode) -> Episode:
    season = db.get(Season, episode.season_id)
    if not season or season.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Cannot publish episode without a season")
    series = db.get(Series, episode.series_id)
    if not series or series.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Cannot publish episode without a series")
    if season.status != "published":
        raise HTTPException(status_code=400, detail="Parent season must be published before publishing an episode")
    if series.status != "published":
        raise HTTPException(status_code=400, detail="Parent series must be published before publishing an episode")
    publish_entity(episode)
    return episode


def make_slug_for_movie(db: Session, title: str, slug: str | None, *, exclude_id: int | None = None) -> str:
    try:
        candidate = slug_or_from_title(slug, title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ensure_unique_movie_slug(db, candidate, exclude_id=exclude_id)
    return candidate


def make_slug_for_series(db: Session, title: str, slug: str | None, *, exclude_id: int | None = None) -> str:
    try:
        candidate = slug_or_from_title(slug, title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ensure_unique_series_slug(db, candidate, exclude_id=exclude_id)
    return candidate
