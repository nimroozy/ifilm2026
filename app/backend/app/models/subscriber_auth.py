"""Subscriber identity, entitlement snapshots, devices, and refresh tokens."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class SubscriberEntitlementSnapshot(Base):
    __tablename__ = "subscriber_entitlement_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    account_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    service_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    package_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    branch_code: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    denial_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_devices: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SubscriberDeviceSession(Base):
    __tablename__ = "subscriber_device_sessions"
    __table_args__ = (
        UniqueConstraint("subscriber_id", "client_device_id", name="uq_subscriber_device_client_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    client_device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    device_type: Mapped[str] = mapped_column(String(32), default="desktop", nullable=False)
    browser: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    ip: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class SubscriberRefreshToken(Base):
    __tablename__ = "subscriber_refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    device_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriber_device_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reuse_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
