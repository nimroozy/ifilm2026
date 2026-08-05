"""Schemas for media upload foundation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import ORMModel

MEDIA_CATEGORIES = ("originals", "posters", "backdrops", "trailers", "subtitles")


class UploadSessionCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(gt=0)
    category: str = "originals"
    movie_id: int | None = None
    series_id: int | None = None
    season_id: int | None = None
    episode_id: int | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in MEDIA_CATEGORIES:
            raise ValueError(f"category must be one of {', '.join(MEDIA_CATEGORIES)}")
        return normalized

    @model_validator(mode="after")
    def single_owner(self) -> UploadSessionCreate:
        owners = [self.movie_id, self.series_id, self.season_id, self.episode_id]
        if sum(1 for owner in owners if owner is not None) > 1:
            raise ValueError("Only one of movie_id, series_id, season_id, episode_id may be set")
        return self


class MediaAssetOut(ORMModel):
    id: str
    movie_id: int | None
    series_id: int | None
    season_id: int | None
    episode_id: int | None
    original_filename: str
    stored_filename: str
    mime_type: str
    extension: str
    size_bytes: int
    checksum_sha256: str | None
    width: int | None
    height: int | None
    duration_seconds: float | None
    storage_backend: str
    storage_path: str | None
    category: str
    upload_status: str
    processing_status: str
    container_format: str | None = None
    overall_bitrate: int | None = None
    video_codec: str | None = None
    video_profile: str | None = None
    display_aspect_ratio: str | None = None
    video_frame_rate: float | None = None
    video_bitrate: int | None = None
    pixel_format: str | None = None
    audio_codec: str | None = None
    audio_channels: int | None = None
    audio_channel_layout: str | None = None
    audio_sample_rate: int | None = None
    audio_bitrate: int | None = None
    audio_stream_count: int | None = None
    subtitle_stream_count: int | None = None
    probe_json: dict | None = None
    probe_version: str | None = None
    probed_at: datetime | None = None
    source_type: str = "uploaded"
    # Masked display URL only — never return raw query/credentials in list/detail APIs.
    external_url: str | None = None
    external_url_masked: str | None = None
    external_kind: str | None = None
    external_content_type: str | None = None
    external_content_length: int | None = None
    external_accept_ranges: bool = False
    external_validated_at: datetime | None = None
    external_is_primary: bool = False
    external_protection_mode: str = "unprotected_direct"
    external_acknowledged_at: datetime | None = None
    created_by_admin_id: int | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UploadSessionOut(ORMModel):
    id: str
    media_asset_id: str
    expected_size_bytes: int
    bytes_received: int
    status: str
    progress_percent: int = 0
    error: str | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    media_asset: MediaAssetOut | None = None


class UploadSessionCreateOut(BaseModel):
    session: UploadSessionOut
    media_asset: MediaAssetOut


class MediaAssetLinkRequest(BaseModel):
    """Attach an existing unassigned asset to a movie or episode."""

    owner_type: str = Field(pattern="^(movie|episode)$")
    owner_id: int = Field(gt=0)


class MediaAssetDetachRequest(BaseModel):
    """Detach ownership. Optionally unpublish when detach would leave published content unplayable."""

    force_unpublish: bool = False


class ExternalMediaAttachRequest(BaseModel):
    """Validate and attach an HTTPS MP4/HLS URL to a movie or episode (Option A)."""

    url: str = Field(min_length=8, max_length=2048)
    owner_type: str = Field(pattern="^(movie|episode)$")
    owner_id: int = Field(gt=0)
    category: str = "originals"
    acknowledge_unprotected_external: bool = False

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in MEDIA_CATEGORIES:
            raise ValueError(f"category must be one of {', '.join(MEDIA_CATEGORIES)}")
        return normalized
