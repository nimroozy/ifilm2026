"""HLS encoding profiles, packages, and renditions (local filesystem)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.media_assets import new_uuid, utcnow

PACKAGE_TYPE_HLS_VOD = "hls_vod"
PACKAGE_ACTIVE_STATUSES = frozenset(
    {"pending", "encoding", "validating", "promoting"}
)
PACKAGE_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


class MediaEncodingProfile(Base):
    __tablename__ = "media_encoding_profiles"
    __table_args__ = (
        Index("ix_media_encoding_profiles_height", "height"),
        Index("ix_media_encoding_profiles_enabled", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    video_bitrate: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_bitrate: Mapped[int] = mapped_column(Integer, nullable=False)
    maxrate: Mapped[int] = mapped_column(Integer, nullable=False)
    bufsize: Mapped[int] = mapped_column(Integer, nullable=False)
    video_codec: Mapped[str] = mapped_column(String(32), nullable=False, default="h264")
    audio_codec: Mapped[str] = mapped_column(String(32), nullable=False, default="aac")
    video_profile: Mapped[str] = mapped_column(String(32), nullable=False, default="main")
    preset: Mapped[str] = mapped_column(String(32), nullable=False, default="veryfast")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    renditions = relationship("MediaRendition", back_populates="profile")


class MediaPackage(Base):
    __tablename__ = "media_packages"
    __table_args__ = (
        Index("ix_media_packages_media_asset_id", "media_asset_id"),
        Index("ix_media_packages_status", "status"),
        Index("ix_media_packages_processing_job_id", "processing_job_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    processing_job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media_processing_jobs.id", ondelete="SET NULL"), nullable=True
    )
    package_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PACKAGE_TYPE_HLS_VOD
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    master_playlist_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    work_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    segment_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    rendition_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    media_asset = relationship("MediaAsset", back_populates="packages")
    processing_job = relationship("MediaProcessingJob", back_populates="package")
    renditions = relationship(
        "MediaRendition",
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="MediaRendition.height",
    )


class MediaRendition(Base):
    __tablename__ = "media_renditions"
    __table_args__ = (
        Index("ix_media_renditions_package_id", "package_id"),
        Index("ix_media_renditions_label", "label"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_packages.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media_encoding_profiles.id", ondelete="SET NULL"), nullable=True
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bandwidth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    average_bandwidth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    playlist_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    video_codec: Mapped[str | None] = mapped_column(String(32), nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    package = relationship("MediaPackage", back_populates="renditions")
    profile = relationship("MediaEncodingProfile", back_populates="renditions")
