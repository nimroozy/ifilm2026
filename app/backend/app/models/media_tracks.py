"""Media track metadata (audio / subtitle) for player selectors."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class MediaTrack(Base):
    """Language-coded track row. UI labels come from frontend i18n, not this table."""

    __tablename__ = "media_tracks"
    __table_args__ = (
        UniqueConstraint(
            "media_asset_id",
            "track_type",
            "language_code",
            name="ix_media_tracks_asset_type_lang",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    track_type: Mapped[str] = mapped_column(String(16), nullable=False)  # audio | subtitle
    language_code: Mapped[str] = mapped_column(String(16), nullable=False)
    # Optional stable key for i18n (e.g. "audio.persian_dub"); never a translated string.
    label_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_dubbed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Sidecar asset (audio/subtitle upload) or embedded stream on the primary asset.
    source_media_asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_stream_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hls_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hls_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
