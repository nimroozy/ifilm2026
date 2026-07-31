"""Watch progress / history API schemas."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class WatchProgressUpdate(BaseModel):
    position_seconds: float
    duration_seconds: float | None = None
    playback_session_id: str | None = Field(default=None, max_length=36)
    device_id: int | None = None
    event_at: datetime | None = None
    start_over: bool = False

    @field_validator("position_seconds", "duration_seconds")
    @classmethod
    def finite_non_nan(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("must be a number")
        if math.isnan(value) or math.isinf(value):
            raise ValueError("must be a finite number")
        return float(value)

    @field_validator("position_seconds")
    @classmethod
    def position_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("position_seconds must be >= 0")
        if value > 86400 * 14:
            raise ValueError("position_seconds is unreasonably large")
        return value

    @field_validator("duration_seconds")
    @classmethod
    def duration_positive(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if value <= 0:
            raise ValueError("duration_seconds must be > 0")
        if value > 86400 * 14:
            raise ValueError("duration_seconds is unreasonably large")
        return value

    @field_validator("event_at")
    @classmethod
    def event_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            raise ValueError("event_at must be timezone-aware")
        return value


class WatchProgressOut(BaseModel):
    id: int
    media_asset_id: str
    content_type: Literal["movie", "episode"]
    movie_id: int | None = None
    episode_id: int | None = None
    series_id: int | None = None
    season_number: int | None = None
    episode_number: int | None = None
    title: str = ""
    subtitle: str = ""
    poster_url: str = ""
    position_seconds: float
    duration_seconds: float
    progress_percent: float
    completed: bool
    available: bool = True
    player_path: str = ""
    first_watched_at: datetime | None = None
    last_watched_at: datetime | None = None
    completed_at: datetime | None = None
    last_event_at: datetime | None = None


class WatchProgressActionOut(BaseModel):
    detail: str = "ok"
    deleted: int = 0
