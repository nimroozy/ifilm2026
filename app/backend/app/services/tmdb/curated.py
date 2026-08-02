"""Curated TMDB ids for the realistic demo seed."""

from __future__ import annotations

from dataclasses import dataclass

REAL_DEMO_SEED_VERSION = "2.0.0"


@dataclass(frozen=True)
class CuratedMovie:
    tmdb_id: int
    status: str
    genres: tuple[str, ...]
    with_demo_clip: bool = False


@dataclass(frozen=True)
class CuratedSeries:
    tmdb_id: int
    mode: str  # fully_published | partial | draft
    seasons: int = 2
    episodes_per_season: int = 3
    with_demo_clips: int = 0


CURATED_MOVIES: tuple[CuratedMovie, ...] = (
    CuratedMovie(27205, "published", ("Action", "Science Fiction", "Thriller"), True),  # Inception
    CuratedMovie(157336, "published", ("Drama", "Science Fiction"), True),  # Interstellar
    CuratedMovie(508943, "published", ("Animation", "Family", "Comedy"), True),  # Luca
    CuratedMovie(515042, "published", ("Documentary",), True),  # Free Solo
    CuratedMovie(12, "published", ("Animation", "Family", "Comedy"), False),  # Finding Nemo
    CuratedMovie(550, "published", ("Drama", "Thriller"), False),  # Fight Club
    CuratedMovie(603, "draft", ("Action", "Science Fiction"), False),  # The Matrix
    CuratedMovie(10681, "draft", ("Family", "Comedy"), False),  # WALL-E
    CuratedMovie(299536, "draft", ("Action", "Science Fiction"), False),  # Avengers: Infinity War
    CuratedMovie(105, "in_review", ("Action", "Comedy", "Science Fiction"), False),  # Back to the Future
    CuratedMovie(13, "approved", ("Drama", "Comedy"), False),  # Forrest Gump
    CuratedMovie(24, "unpublished", ("Action", "Thriller"), False),  # Kill Bill Vol. 1
)


CURATED_SERIES: tuple[CuratedSeries, ...] = (
    CuratedSeries(1399, "fully_published", with_demo_clips=2),  # Game of Thrones
    CuratedSeries(82856, "partial", with_demo_clips=2),  # The Mandalorian
    CuratedSeries(66732, "draft", with_demo_clips=0),  # Stranger Things
)
