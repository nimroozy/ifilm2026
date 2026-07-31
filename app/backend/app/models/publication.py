"""Publication workflow audit events."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class MediaPublicationEvent(Base):
    """Immutable history of publication status transitions."""

    __tablename__ = "media_publication_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, default="transition", index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
