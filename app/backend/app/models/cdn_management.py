"""Admin-managed CDN inventory, routing, credentials and provisioning state."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.media_assets import new_uuid


def utcnow() -> datetime:
    return datetime.now(UTC)


class ManagedCDNNode(Base):
    __tablename__ = "managed_cdn_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # main | cache
    host: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    ssh_port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    ssh_username: Mapped[str] = mapped_column(String(128), nullable=False)
    credential_type: Mapped[str] = mapped_column(String(16), nullable=False, default="password")
    credential_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    branch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    draining: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cache_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disk_total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disk_free_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cached_objects: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cached_titles: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cache_hits: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cache_misses: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bandwidth_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    rtt_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    software_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    health_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    provision_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_admin_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CDNPrefixRoute(Base):
    __tablename__ = "cdn_prefix_routes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    cidr: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    prefix_length: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("managed_cdn_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CDNProvisionRun(Base):
    __tablename__ = "cdn_provision_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("managed_cdn_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    log_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requested_by_admin_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
