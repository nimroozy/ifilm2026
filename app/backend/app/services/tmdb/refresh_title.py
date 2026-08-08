"""Per-title TMDB refresh — updates TMDB-owned metadata only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.content import Movie, Series
from app.services.tmdb.client import TMDBClient
from app.services.tmdb.credits import sync_movie_credits, sync_series_credits
from app.services.tmdb.import_service import (
    _apply_trailer,
    _base_movie_fields,
    _dedupe_imdb,
    _ensure_genres,
)
from app.services.tmdb.trailers import select_trailer
from app.services.similar_content import similar_status


def utcnow() -> datetime:
    return datetime.now(UTC)


# Fields that admins may edit manually — never overwritten by TMDB refresh.
_MOVIE_PRESERVE = {
    "title",
    "original_title",
    "description",
    "short_description",
    "slug",
    "age_rating",
    "poster_url",
    "backdrop_url",
    "logo_url",
    "audio",
    "subtitles",
    "dubbed",
    "qualities",
    "director",
    "producer",
    "writer",
    "studio",
    "status",
    "hls_path",
}


@dataclass
class TitleRefreshResult:
    media_type: str
    entity_id: int
    tmdb_id: int
    trailer_updated: bool = False
    credits_count: int = 0
    similar_count: int = 0
    warnings: list[str] = field(default_factory=list)


def refresh_movie_tmdb_details(
    db: Session,
    settings: Settings,
    movie: Movie,
    *,
    client: TMDBClient | None = None,
    overwrite_text: bool = False,
) -> TitleRefreshResult:
    """Refresh trailer + credits (+ optional TMDB text fields). Preserves manual edits by default."""
    if not movie.tmdb_id:
        raise ValueError("movie_has_no_tmdb_id")
    client = client or TMDBClient(settings)
    details = client.movie_details(int(movie.tmdb_id))
    videos = client.movie_videos(int(movie.tmdb_id))
    trailer = select_trailer(videos, language=settings.tmdb_language)

    if overwrite_text:
        fields = _base_movie_fields(details, settings)
        fields["imdb_id"] = _dedupe_imdb(db, Movie, fields.get("imdb_id"), movie.id)
        for key, value in fields.items():
            if key in _MOVIE_PRESERVE:
                continue
            setattr(movie, key, value)
        movie.genre_links = _ensure_genres(db, details)
    else:
        # Safe TMDB-owned scalars only.
        if details.get("vote_average") is not None and movie.imdb_rating is None:
            movie.imdb_rating = details.get("vote_average")
        external = (details.get("external_ids") or {}).get("imdb_id") or details.get("imdb_id")
        if external and not movie.imdb_id:
            movie.imdb_id = _dedupe_imdb(db, Movie, str(external), movie.id)
        if details.get("spoken_languages"):
            movie.spoken_languages = details.get("spoken_languages") or []

    had_trailer = bool(movie.trailer_key)
    _apply_trailer(movie, trailer)
    movie.metadata_source = movie.metadata_source or "tmdb"
    movie.metadata_updated_at = utcnow()
    db.add(movie)
    db.flush()

    credits_count = sync_movie_credits(db, settings, movie, client=client)
    status = similar_status(db, movie)
    return TitleRefreshResult(
        media_type="movie",
        entity_id=movie.id,
        tmdb_id=int(movie.tmdb_id),
        trailer_updated=bool(trailer) or had_trailer,
        credits_count=credits_count,
        similar_count=int(status["similar_count"]),
    )


def refresh_series_tmdb_details(
    db: Session,
    settings: Settings,
    series: Series,
    *,
    client: TMDBClient | None = None,
) -> TitleRefreshResult:
    if not series.tmdb_id:
        raise ValueError("series_has_no_tmdb_id")
    client = client or TMDBClient(settings)
    videos = client.tv_videos(int(series.tmdb_id))
    trailer = select_trailer(videos, language=settings.tmdb_language)
    _apply_trailer(series, trailer)
    series.metadata_updated_at = utcnow()
    db.add(series)
    db.flush()
    credits_count = sync_series_credits(db, settings, series, client=client)
    return TitleRefreshResult(
        media_type="series",
        entity_id=series.id,
        tmdb_id=int(series.tmdb_id),
        trailer_updated=bool(trailer),
        credits_count=credits_count,
        similar_count=0,
    )
