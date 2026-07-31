"""Media processing jobs and diagnostic events (probe foundation)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.media_assets import new_uuid, utcnow

# Active statuses that block a second probe job for the same asset.
ACTIVE_JOB_STATUSES = frozenset({"queued", "running", "retry_wait"})
TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "cancelled"})
JOB_TYPE_PROBE = "probe"
# Reserved for later phases (not implemented here): encode, hls_package


class MediaProcessingJob(Base):
    __tablename__ = "media_processing_jobs"
    __table_args__ = (
        Index("ix_media_processing_jobs_status", "status"),
        Index("ix_media_processing_jobs_media_asset_id", "media_asset_id"),
        Index("ix_media_processing_jobs_next_retry_at", "next_retry_at"),
        Index("ix_media_processing_jobs_priority", "priority"),
        Index("ix_media_processing_jobs_heartbeat_at", "heartbeat_at"),
        # At most one active probe job per asset (queued/running/retry_wait).
        Index(
            "uq_media_processing_active_probe",
            "media_asset_id",
            "job_type",
            unique=True,
            sqlite_where=text(
                "status IN ('queued', 'running', 'retry_wait') AND job_type = 'probe'"
            ),
            postgresql_where=text(
                "status IN ('queued', 'running', 'retry_wait') AND job_type = 'probe'"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, default=JOB_TYPE_PROBE)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    media_asset = relationship("MediaAsset", back_populates="processing_jobs")
    events = relationship(
        "MediaProcessingJobEvent",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="MediaProcessingJobEvent.created_at",
    )


class MediaProcessingJobEvent(Base):
    __tablename__ = "media_processing_job_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("media_processing_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job = relationship("MediaProcessingJob", back_populates="events")
