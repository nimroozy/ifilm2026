"""Public recommendation API schemas (no private/source fields)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RecommendationItemOut(BaseModel):
    content_type: Literal["movie", "series"]
    id: int
    slug: str
    title: str
    poster_url: str = ""
    backdrop_url: str = ""
    release_year: int | None = None
    imdb_rating: float | None = None
    genres: list[str] = Field(default_factory=list)
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    explanation: str | None = None
    playable: bool = False
    detail_path: str = ""
    components: dict[str, float] | None = None


class RecommendationListOut(BaseModel):
    mode: Literal["personalized", "popular", "item", "what_to_watch"] = "personalized"
    personalized: bool = False
    label: str = "Recommended for You"
    count: int = 0
    items: list[RecommendationItemOut] = Field(default_factory=list)


class RecommendationShelfOut(BaseModel):
    shelf_type: str
    title: str
    personalized: bool = False
    source: dict[str, Any] | None = None
    collections: list[dict[str, Any]] | None = None
    items: list[RecommendationItemOut] = Field(default_factory=list)


class HomeRecommendationsOut(BaseModel):
    mode: str
    personalized: bool = False
    preference_summary: dict[str, Any] | None = None
    shelves: list[RecommendationShelfOut] = Field(default_factory=list)


class WhatToWatchIn(BaseModel):
    content_type: Literal["movie", "series", "either"] = "either"
    genre: str | None = None
    mood: str | None = None
    duration: Literal["under_90", "90_120", "over_120", "any"] | None = "any"
    language: str | None = "any"
    subtitles: Literal["required", "optional", "any"] | None = "optional"
    release_period: Literal["new", "modern", "classic", "any"] | None = "any"
    limit: int = Field(8, ge=3, le=10)


class WhatToWatchOut(BaseModel):
    mode: Literal["what_to_watch"] = "what_to_watch"
    ai: bool = False
    filters: dict[str, Any] = Field(default_factory=dict)
    relaxed: list[str] = Field(default_factory=list)
    count: int = 0
    items: list[RecommendationItemOut] = Field(default_factory=list)


class RecommendationInspectOut(BaseModel):
    subscriber_id: int | None = None
    username: str | None = None
    mode: str | None = None
    preference_signals: dict[str, Any] | None = None
    weights: dict[str, float] | None = None
    candidates: list[RecommendationItemOut] = Field(default_factory=list)
    error: str | None = None
