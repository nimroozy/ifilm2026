"""Homepage aggregate response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.collections import CollectionPublicOut
from app.schemas.content import MovieOut, SeriesOut
from app.schemas.recommendations import HomeRecommendationsOut
from app.schemas.watch_history import WatchProgressOut
from app.schemas.watchlist import WatchlistItemOut


class CatalogHomeOut(BaseModel):
    featured: list[MovieOut] = Field(default_factory=list)
    trending: list[MovieOut] = Field(default_factory=list)
    recently_added: list[MovieOut] = Field(default_factory=list)
    top_rated: list[MovieOut] = Field(default_factory=list)
    action: list[MovieOut] = Field(default_factory=list)
    comedy: list[MovieOut] = Field(default_factory=list)
    afghan: list[MovieOut] = Field(default_factory=list)
    persian_dubbed: list[MovieOut] = Field(default_factory=list)
    pashto_dubbed: list[MovieOut] = Field(default_factory=list)
    family: list[MovieOut] = Field(default_factory=list)
    popular_series: list[SeriesOut] = Field(default_factory=list)
    featured_collections: list[CollectionPublicOut] = Field(default_factory=list)


class MeHomeOut(CatalogHomeOut):
    continue_watching: list[WatchProgressOut] = Field(default_factory=list)
    watchlist: list[WatchlistItemOut] = Field(default_factory=list)
    recommendations: HomeRecommendationsOut | dict[str, Any] | None = None
