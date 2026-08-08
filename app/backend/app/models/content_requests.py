"""Subscriber content requests (movie/series) and admin workflow audit events."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

REQUEST_TYPES = frozenset({"movie", "series"})
REQUEST_STATUSES = frozenset(
    {"new", "reviewing", "approved", "rejected", "added", "withdrawn"}
)
OPEN_STATUSES = frozenset({"new", "reviewing", "approved"})
WITHDRAWABLE_STATUSES = frozenset({"new", "reviewing"})


def utcnow() -> datetime:
    return datetime.now(UTC)


class ContentRequest(Base):
    __tablename__ = "content_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    imdb_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    tmdb_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    imdb_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new", index=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_response: Mapped[str | None] = mapped_column(String(512), nullable=True)
    linked_movie_id: Mapped[int | None] = mapped_column(
        ForeignKey("movies.id", ondelete="SET NULL"), nullable=True
    )
    linked_series_id: Mapped[int | None] = mapped_column(
        ForeignKey("series.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ContentRequestEvent(Base):
    __tablename__ = "content_request_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_request_id: Mapped[int] = mapped_column(
        ForeignKey("content_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    actor_subscriber_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscribers.id", ondelete="SET NULL"), nullable=True
    )
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
