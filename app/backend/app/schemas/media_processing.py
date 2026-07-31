"""Schemas for media processing jobs, probe metadata, and HLS packages."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.media_upload import MediaAssetOut


class MediaAssetProbeOut(MediaAssetOut):
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
    probe_version: str | None = None
    probed_at: datetime | None = None
    # Filtered probe JSON only — never raw unrestricted stderr.
    probe_json: dict[str, Any] | None = None


class ProcessingJobEventOut(ORMModel):
    id: str
    job_id: str
    event_type: str
    message: str | None = None
    created_at: datetime | None = None


class ProcessingJobOut(ORMModel):
    id: str
    media_asset_id: str
    job_type: str
    status: str
    priority: int
    attempt_count: int
    max_attempts: int
    progress_percent: int
    current_step: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    worker_id: str | None = None
    cancel_requested: bool = False
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    next_retry_at: datetime | None = None
    created_by_admin_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    media_asset: MediaAssetProbeOut | None = None
    events: list[ProcessingJobEventOut] = Field(default_factory=list)


class ProcessingJobCreateOut(BaseModel):
    job: ProcessingJobOut
    created: bool


class EncodeJobCreateOut(BaseModel):
    job: ProcessingJobOut
    package: MediaPackageOut
    created: bool


class ProcessingStatusOut(BaseModel):
    enabled: bool
    hls_encoding_enabled: bool
    ffmpeg_available: bool
    ffprobe_available: bool


class EncodingProfileOut(ORMModel):
    id: str
    name: str
    label: str
    height: int
    video_bitrate: int
    audio_bitrate: int
    maxrate: int
    bufsize: int
    video_codec: str
    audio_codec: str
    video_profile: str
    preset: str
    enabled: bool
    sort_order: int


class MediaRenditionOut(ORMModel):
    id: str
    package_id: str
    profile_id: str | None = None
    label: str
    height: int
    width: int | None = None
    bandwidth: int | None = None
    average_bandwidth: int | None = None
    playlist_path: str | None = None
    segment_count: int = 0
    video_codec: str | None = None
    audio_codec: str | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MediaPackageOut(ORMModel):
    id: str
    media_asset_id: str
    processing_job_id: str | None = None
    package_type: str
    status: str
    storage_path: str | None = None
    master_playlist_path: str | None = None
    source_width: int | None = None
    source_height: int | None = None
    duration_seconds: float | None = None
    segment_duration_seconds: int
    rendition_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    created_by_admin_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    renditions: list[MediaRenditionOut] = Field(default_factory=list)
