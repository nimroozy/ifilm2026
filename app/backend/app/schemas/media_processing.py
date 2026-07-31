"""Schemas for media processing jobs and probe metadata."""

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


class ProcessingStatusOut(BaseModel):
    enabled: bool
    ffmpeg_available: bool
    ffprobe_available: bool
