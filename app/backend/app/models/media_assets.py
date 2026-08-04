"""Media asset and upload session models for local upload foundation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_uuid() -> str:
    return str(uuid.uuid4())


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN movie_id IS NOT NULL THEN 1 ELSE 0 END)"
            " + (CASE WHEN series_id IS NOT NULL THEN 1 ELSE 0 END)"
            " + (CASE WHEN season_id IS NOT NULL THEN 1 ELSE 0 END)"
            " + (CASE WHEN episode_id IS NOT NULL THEN 1 ELSE 0 END) <= 1",
            name="ck_media_assets_single_owner",
        ),
        # Concurrent finalize safety: at most one completed asset per checksum.
        Index(
            "uq_media_assets_completed_checksum",
            "checksum_sha256",
            unique=True,
            sqlite_where=text("upload_status = 'completed' AND checksum_sha256 IS NOT NULL"),
            postgresql_where=text("upload_status = 'completed' AND checksum_sha256 IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    movie_id: Mapped[int | None] = mapped_column(
        ForeignKey("movies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("series.id", ondelete="SET NULL"), nullable=True, index=True
    )
    season_id: Mapped[int | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    episode_id: Mapped[int | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="SET NULL"), nullable=True, index=True
    )

    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    extension: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    storage_backend: Mapped[str] = mapped_column(String(32), default="local")
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    category: Mapped[str] = mapped_column(String(32), default="originals")
    upload_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    processing_status: Mapped[str] = mapped_column(String(32), default="none", index=True)

    # uploaded = local file; external = validated HTTPS MP4/HLS URL
    source_type: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    external_content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_content_length: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    external_accept_ranges: Mapped[bool] = mapped_column(Boolean, default=False)
    external_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Probed metadata (ffprobe). Null until a successful probe completes.
    container_format: Mapped[str | None] = mapped_column(String(64), nullable=True)
    overall_bitrate: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    video_codec: Mapped[str | None] = mapped_column(String(64), nullable=True)
    video_profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_aspect_ratio: Mapped[str | None] = mapped_column(String(32), nullable=True)
    video_frame_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    video_bitrate: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pixel_format: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_channel_layout: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_bitrate: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    audio_stream_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subtitle_stream_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    probe_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    probe_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    probed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    sessions = relationship(
        "UploadSession", back_populates="media_asset", cascade="all, delete-orphan"
    )
    processing_jobs = relationship(
        "MediaProcessingJob", back_populates="media_asset", cascade="all, delete-orphan"
    )
    packages = relationship(
        "MediaPackage", back_populates="media_asset", cascade="all, delete-orphan"
    )


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expected_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bytes_received: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    temp_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id"), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    media_asset = relationship("MediaAsset", back_populates="sessions")
