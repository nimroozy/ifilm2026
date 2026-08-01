from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemUpdateJob(Base):
    __tablename__ = "system_update_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="queued")
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="stable")
    current_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_admin_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_users.id"), nullable=True
    )
    backup_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    previous_migration_head: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resulting_migration_head: Mapped[str | None] = mapped_column(String(128), nullable=True)
    release_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preflight_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rollback_result: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SystemUpdateEvent(Base):
    __tablename__ = "system_update_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("system_update_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
