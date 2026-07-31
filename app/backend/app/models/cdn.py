from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    cdn: Mapped[str] = mapped_column(String(255), default="")
    ip_ranges: Mapped[str] = mapped_column(String(512), default="")
    active_users: Mapped[int] = mapped_column(Integer, default=0)
    concurrent_viewers: Mapped[int] = mapped_column(Integer, default=0)
    streaming_traffic: Mapped[str] = mapped_column(String(64), default="0 Mbps")
    cdn_status: Mapped[str] = mapped_column(String(32), default="healthy")


class CDNNode(Base):
    __tablename__ = "cdn_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    location: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(32), default="online")
    ip: Mapped[str] = mapped_column(String(64), default="")
    base_url: Mapped[str] = mapped_column(String(1024), default="")
    storage_capacity: Mapped[int] = mapped_column(Integer, default=0)
    storage_used: Mapped[int] = mapped_column(Integer, default=0)
    network_usage: Mapped[int] = mapped_column(Integer, default=0)
    current_viewers: Mapped[int] = mapped_column(Integer, default=0)
    cached_titles: Mapped[int] = mapped_column(Integer, default=0)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_score: Mapped[int] = mapped_column(Integer, default=100)
    cache_hit_rate: Mapped[float] = mapped_column(Float, default=0.0)
    branch: Mapped[str] = mapped_column(String(100), default="")


class CDNSyncJob(Base):
    __tablename__ = "cdn_sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("cdn_nodes.id"), index=True)
    content_type: Mapped[str] = mapped_column(String(32), default="movie")
    content_id: Mapped[int] = mapped_column(Integer, nullable=False)
    hls_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending|syncing|completed|failed
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
