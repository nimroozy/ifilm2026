"""Schemas for media track metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TrackType = Literal["audio", "subtitle"]


class MediaTrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    media_asset_id: str
    track_type: TrackType
    language_code: str
    label_key: str | None = None
    is_default: bool = False
    is_dubbed: bool = False
    source_media_asset_id: str | None = None
    source_stream_index: int | None = None
    hls_group_id: str | None = None
    hls_name: str | None = None
    sort_order: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MediaTrackCreate(BaseModel):
    track_type: TrackType
    language_code: str = Field(min_length=2, max_length=16)
    label_key: str | None = Field(default=None, max_length=64)
    is_default: bool = False
    is_dubbed: bool = False
    source_media_asset_id: str | None = Field(default=None, max_length=36)
    source_stream_index: int | None = Field(default=None, ge=0, le=64)
    hls_group_id: str | None = Field(default=None, max_length=64)
    hls_name: str | None = Field(default=None, max_length=128)
    sort_order: int = 0


class MediaTrackUpdate(BaseModel):
    language_code: str | None = Field(default=None, min_length=2, max_length=16)
    label_key: str | None = Field(default=None, max_length=64)
    is_default: bool | None = None
    is_dubbed: bool | None = None
    source_media_asset_id: str | None = Field(default=None, max_length=36)
    source_stream_index: int | None = Field(default=None, ge=0, le=64)
    hls_group_id: str | None = Field(default=None, max_length=64)
    hls_name: str | None = Field(default=None, max_length=128)
    sort_order: int | None = None


class MediaTrackListOut(BaseModel):
    items: list[MediaTrackOut]
    audio: list[MediaTrackOut] = Field(default_factory=list)
    subtitles: list[MediaTrackOut] = Field(default_factory=list)
