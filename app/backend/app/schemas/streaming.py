"""Schemas for protected playback sessions (no tokens/hashes/paths in list outputs)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class PlaybackSessionCreate(BaseModel):
    """Admin create by media asset id."""

    media_asset_id: str


class CustomerPlaybackSessionCreate(BaseModel):
    """Player create by asset id or catalog content reference."""

    media_asset_id: str | None = None
    content_type: Literal["movie", "episode"] | None = None
    content_id: int | None = None

    @model_validator(mode="after")
    def require_one_target(self) -> CustomerPlaybackSessionCreate:
        has_asset = bool(self.media_asset_id)
        has_content = self.content_type is not None and self.content_id is not None
        if has_asset == has_content:
            raise ValueError(
                "Provide either media_asset_id or content_type+content_id (exactly one)"
            )
        return self


class PlaybackSessionCreated(BaseModel):
    id: str
    media_asset_id: str
    media_package_id: str
    expires_at: datetime
    playback_token: str = Field(description="Returned once; never stored or logged")
    master_playlist_url: str


class PlaybackSessionOut(ORMModel):
    id: str
    media_asset_id: str
    media_package_id: str
    principal_type: str
    principal_id: str
    status: str
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime | None = None
    last_accessed_at: datetime | None = None
    created_by_admin_id: int | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    revoke_reason: str | None = None
    access_count: int = 0


class PlaybackSessionRevokeResult(BaseModel):
    revoked: int


class StreamingStatusOut(BaseModel):
    enabled: bool
    supported_principals: list[str]
    subscriber_entitlement: str
