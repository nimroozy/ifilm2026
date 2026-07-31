from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
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
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("subscriber_id", "content_type", "content_id", name="uq_watchlist"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id", ondelete="CASCADE"), index=True)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
