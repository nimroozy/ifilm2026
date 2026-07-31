"""Watch progress models for authenticated subscribers."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class UserWatchProgress(Base):
    """One canonical progress row per subscriber and playable media asset."""

    __tablename__ = "user_watch_progress"
    __table_args__ = (
        UniqueConstraint("subscriber_id", "media_asset_id", name="uq_user_watch_progress_asset"),
        CheckConstraint(
            "(movie_id IS NOT NULL AND episode_id IS NULL) OR (movie_id IS NULL AND episode_id IS NOT NULL)",
            name="ck_user_watch_progress_one_owner",
        ),
        CheckConstraint("position_seconds >= 0", name="ck_user_watch_progress_position_nonneg"),
        CheckConstraint("duration_seconds > 0", name="ck_user_watch_progress_duration_pos"),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_user_watch_progress_percent_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movie_id: Mapped[int | None] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    episode_id: Mapped[int | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    playback_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    device_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    progress_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    first_watched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_watched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


# Keep SQLAlchemy metadata aware of the dropped stub name for clarity in docs only.
# The ORM class WatchHistory is removed; table watch_history is dropped in 009.
