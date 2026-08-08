from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Subscriber(Base):
    __tablename__ = "subscribers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    # Local password hashes only (Argon2). Never store Radius credentials.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    branch: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    package: Mapped[str] = mapped_column(String(100), default="")
    expiration: Mapped[str] = mapped_column(String(32), default="")
    last_activity: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    viewing_time: Mapped[int] = mapped_column(Integer, default=0)
    radius_synced: Mapped[bool] = mapped_column(Boolean, default=False)
    identity_provider: Mapped[str] = mapped_column(String(32), default="local", index=True)
    external_subject: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    max_devices: Mapped[int] = mapped_column(Integer, default=3)
    service_status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Device(Base):
    """Legacy stub table from initial schema — unused by Phase 11 APIs.

    Prefer ``SubscriberDeviceSession`` for device management.
    """

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    type: Mapped[str] = mapped_column(String(32), default="desktop")
    browser: Mapped[str] = mapped_column(String(100), default="")
    last_active: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    current: Mapped[bool] = mapped_column(Boolean, default=False)


class WatchlistItem(Base):
    """Subscriber watchlist membership — exactly one of movie_id / series_id."""

    __tablename__ = "watchlist_items"
    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL AND series_id IS NULL) OR (movie_id IS NULL AND series_id IS NOT NULL)",
            name="ck_watchlist_items_one_owner",
        ),
        Index(
            "uq_watchlist_items_movie",
            "subscriber_id",
            "movie_id",
            unique=True,
            sqlite_where=text("movie_id IS NOT NULL"),
            postgresql_where=text("movie_id IS NOT NULL"),
        ),
        Index(
            "uq_watchlist_items_series",
            "subscriber_id",
            "series_id",
            unique=True,
            sqlite_where=text("series_id IS NOT NULL"),
            postgresql_where=text("series_id IS NOT NULL"),
        ),
        Index("ix_watchlist_items_subscriber_created", "subscriber_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id", ondelete="CASCADE"), index=True)
    movie_id: Mapped[int | None] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
