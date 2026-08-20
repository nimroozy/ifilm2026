"""Durable branch cache-node registry (hybrid CDN Phase 3 control plane)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.media_assets import new_uuid


def utcnow() -> datetime:
    return datetime.now(UTC)


# Lifecycle values stored in ``status``.
STATUS_PENDING = "pending"
STATUS_ONLINE = "online"
STATUS_DEGRADED = "degraded"
STATUS_OFFLINE = "offline"
STATUS_DISABLED = "disabled"

HEALTH_UNKNOWN = "unknown"
HEALTH_HEALTHY = "healthy"
HEALTH_UNHEALTHY = "unhealthy"


class BranchCacheNode(Base):
    """Operator-managed branch pull-through cache node (control plane only).

    Does not store enrollment secrets in cleartext, private signing keys,
    Portal/SAS values, or customer data. Heartbeat bootstrap hashes only.
    """

    __tablename__ = "branch_cache_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    node_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    site_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    branch_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_PENDING)
    draining: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    software_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    protocol_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    capacity_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_health_ok_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    health_status: Mapped[str] = mapped_column(String(32), nullable=False, default=HEALTH_UNKNOWN)
    # SHA-256 hex of one-time enrollment/heartbeat bootstrap token (never cleartext).
    heartbeat_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    node_public_key_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    node_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_admin_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
