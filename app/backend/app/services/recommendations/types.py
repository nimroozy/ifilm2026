"""Internal recommendation types (not API schemas)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ContentKind = Literal["movie", "series"]


@dataclass
class ContentRef:
    kind: ContentKind
    id: int


@dataclass
class PreferenceProfile:
    subscriber_id: int | None
    preferred_genres: dict[str, float] = field(default_factory=dict)
    preferred_content_types: dict[str, float] = field(default_factory=dict)
    preferred_languages: dict[str, float] = field(default_factory=dict)
    preferred_dubbed_languages: dict[str, float] = field(default_factory=dict)
    preferred_subtitle_languages: dict[str, float] = field(default_factory=dict)
    preferred_countries: dict[str, float] = field(default_factory=dict)
    preferred_actors: dict[str, float] = field(default_factory=dict)  # name lower → weight
    preferred_actor_ids: dict[int, float] = field(default_factory=dict)  # tmdb person id
    preferred_runtime_min: int | None = None
    preferred_runtime_max: int | None = None
    preferred_year_min: int | None = None
    preferred_year_max: int | None = None
    watched_movie_ids: set[int] = field(default_factory=set)
    watched_series_ids: set[int] = field(default_factory=set)
    watchlisted_movie_ids: set[int] = field(default_factory=set)
    watchlisted_series_ids: set[int] = field(default_factory=set)
    dismissed_movie_ids: set[int] = field(default_factory=set)
    dismissed_series_ids: set[int] = field(default_factory=set)
    completed_movie_ids: set[int] = field(default_factory=set)
    completed_series_ids: set[int] = field(default_factory=set)
    continue_watching_movie_ids: set[int] = field(default_factory=set)
    continue_watching_series_ids: set[int] = field(default_factory=set)
    seed_titles: list[tuple[ContentKind, int, str, float]] = field(default_factory=list)
    # (kind, id, title, strength) for "Because You Watched"
    has_personal_signals: bool = False


@dataclass
class ScoredCandidate:
    kind: ContentKind
    id: int
    title: str
    slug: str
    poster_url: str
    backdrop_url: str
    release_year: int | None
    imdb_rating: float | None
    genres: list[str]
    language: str
    country: str
    duration_minutes: int | None
    views: int
    published_at_ts: float
    score: float
    reasons: list[str]
    components: dict[str, float] = field(default_factory=dict)
    playable: bool = False

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.id}"
