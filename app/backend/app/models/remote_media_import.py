"""Remote media import state (server-to-server URL → protected local origin)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.media_assets import new_uuid, utcnow


class RemoteMediaImport(Base):
    """Companion row for remote_media_import processing jobs (secret-safe)."""

    __tablename__ = "remote_media_imports"
    __table_args__ = (
        Index("ix_remote_media_imports_job_id", "processing_job_id", unique=True),
        Index("ix_remote_media_imports_asset_id", "media_asset_id"),
        Index("ix_remote_media_imports_owner", "owner_type", "owner_id"),
        # At most one active import per owner (movie/episode).
        Index(
            "uq_remote_media_imports_active_owner",
            "owner_type",
            "owner_id",
            unique=True,
            sqlite_where=text("phase NOT IN ('completed', 'failed', 'cancelled')"),
            postgresql_where=text("phase NOT IN ('completed', 'failed', 'cancelled')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    processing_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_processing_jobs.id", ondelete="CASCADE"), nullable=False
    )
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    owner_type: Mapped[str] = mapped_column(String(16), nullable=False)  # movie | episode
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    destination: Mapped[str] = mapped_column(String(32), nullable=False, default="local_origin")
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    source_url_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    source_url_display: Mapped[str] = mapped_column(String(512), nullable=False)
    source_host: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_length: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    accept_ranges: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bytes_downloaded: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transfer_rate_bps: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    eta_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    transfer_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    transfer_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_progress_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
