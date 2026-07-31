"""Schemas for protected playback sessions (no tokens/hashes/paths in list outputs)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class PlaybackSessionCreate(BaseModel):
    media_asset_id: str


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
