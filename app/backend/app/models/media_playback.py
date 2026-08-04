"""Playback sessions for protected HLS streaming."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.media_assets import new_uuid, utcnow

PRINCIPAL_ADMIN = "admin"
PRINCIPAL_SUBSCRIBER = "subscriber"

SESSION_ACTIVE = "active"
SESSION_REVOKED = "revoked"
SESSION_EXPIRED = "expired"


class MediaPlaybackSession(Base):
    __tablename__ = "media_playback_sessions"
    __table_args__ = (
        Index("ix_media_playback_sessions_token_hash", "token_hash", unique=True),
        Index("ix_media_playback_sessions_media_asset_id", "media_asset_id"),
        Index("ix_media_playback_sessions_media_package_id", "media_package_id"),
        Index("ix_media_playback_sessions_principal", "principal_type", "principal_id"),
        Index("ix_media_playback_sessions_status", "status"),
        Index("ix_media_playback_sessions_expires_at", "expires_at"),
        Index("ix_media_playback_sessions_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    media_package_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media_packages.id", ondelete="CASCADE"), nullable=True
    )
    principal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=SESSION_ACTIVE)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id"), nullable=True
    )
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    device_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriber_device_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    media_asset = relationship("MediaAsset")
    media_package = relationship("MediaPackage")
