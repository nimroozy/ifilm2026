"""Curated TMDB ids for the realistic demo seed (v3)."""

from __future__ import annotations

from dataclasses import dataclass

REAL_DEMO_SEED_VERSION = "3.0.0"


@dataclass(frozen=True)
class CuratedMovie:
    tmdb_id: int
    status: str
    genres: tuple[str, ...]
    with_demo_clip: bool = False
    featured: bool = False
    trending: bool = False


@dataclass(frozen=True)
class CuratedSeries:
    tmdb_id: int
    mode: str  # fully_published | partial | draft
    seasons: int = 2
    episodes_per_season: int = 3
    with_demo_clips: int = 0
    featured: bool = False
    trending: bool = False


# Stable TMDB IDs (not title search). Genre annotations document shelf coverage;
# live genre rows still come from TMDB import metadata.
CURATED_MOVIES: tuple[CuratedMovie, ...] = (
    # Published + demo clips (6+)
    CuratedMovie(27205, "published", ("Action", "Science Fiction", "Thriller"), True, True, True),  # Inception
    CuratedMovie(157336, "published", ("Drama", "Science Fiction"), True, True, True),  # Interstellar
    CuratedMovie(508943, "published", ("Animation", "Family", "Comedy"), True, True, False),  # Luca
    CuratedMovie(515042, "published", ("Documentary",), True, False, True),  # Free Solo
    CuratedMovie(12, "published", ("Animation", "Family", "Comedy"), True, False, True),  # Finding Nemo
    CuratedMovie(11, "published", ("Action", "Science Fiction"), True, True, False),  # Star Wars
    # Published metadata / trailer only
    CuratedMovie(550, "published", ("Drama", "Thriller"), False, False, True),  # Fight Club
    CuratedMovie(278, "published", ("Drama",), False, True, False),  # The Shawshank Redemption
    CuratedMovie(862, "published", ("Animation", "Family", "Comedy"), False, False, True),  # Toy Story
    CuratedMovie(680, "published", ("Thriller", "Comedy"), False, False, False),  # Pulp Fiction
    # Non-published status paths
    CuratedMovie(603, "draft", ("Action", "Science Fiction"), False),  # The Matrix
    CuratedMovie(10681, "draft", ("Animation", "Family", "Comedy"), False),  # WALL-E
    CuratedMovie(299536, "draft", ("Action", "Science Fiction"), False),  # Avengers: Infinity War
    CuratedMovie(105, "in_review", ("Action", "Comedy", "Science Fiction"), False),  # Back to the Future
    CuratedMovie(13, "approved", ("Drama", "Comedy"), False),  # Forrest Gump
    CuratedMovie(24, "unpublished", ("Action", "Thriller"), False),  # Kill Bill Vol. 1
)


CURATED_SERIES: tuple[CuratedSeries, ...] = (
    CuratedSeries(1399, "fully_published", with_demo_clips=2, featured=True, trending=True),  # Game of Thrones
    CuratedSeries(82856, "partial", with_demo_clips=2, featured=True, trending=True),  # The Mandalorian
    CuratedSeries(1396, "fully_published", with_demo_clips=2, featured=False, trending=True),  # Breaking Bad
    CuratedSeries(94605, "partial", with_demo_clips=2, featured=True, trending=False),  # Arcane
    CuratedSeries(66732, "draft", with_demo_clips=0),  # Stranger Things
)


def curated_movie_clip_count() -> int:
    return sum(1 for m in CURATED_MOVIES if m.with_demo_clip)


def curated_episode_clip_count() -> int:
    return sum(s.with_demo_clips for s in CURATED_SERIES)
