"""Subscriber watchlist API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class WatchlistAddIn(BaseModel):
    movie_id: int | None = Field(default=None, ge=1)
    series_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def one_owner(self) -> WatchlistAddIn:
        has_movie = self.movie_id is not None
        has_series = self.series_id is not None
        if has_movie == has_series:
            raise ValueError("Exactly one of movie_id or series_id is required")
        return self


class WatchlistItemOut(BaseModel):
    id: int
    content_type: Literal["movie", "series"]
    movie_id: int | None = None
    series_id: int | None = None
    title: str = ""
    poster_url: str = ""
    backdrop_url: str = ""
    release_year: int | None = None
    available: bool = True
    detail_path: str = ""
    player_path: str = ""
    created_at: datetime | None = None


class WatchlistActionOut(BaseModel):
    detail: str = "ok"
    deleted: int = 0


class WatchlistMembershipOut(BaseModel):
    in_watchlist: bool
    item_id: int | None = None
