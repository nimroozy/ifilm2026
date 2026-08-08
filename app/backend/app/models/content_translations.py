"""Localized catalog text (manual / TMDB) stored for page loads without TMDB calls."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.media_assets import utcnow

LOCALES = ("en", "fa", "ps")
SOURCES = ("manual", "tmdb", "fallback")
ENTITY_TYPES = ("movie", "series", "episode", "season", "collection")
FIELD_KEYS = (
    "title",
    "overview",
    "description",
    "short_description",
    "tagline",
    "name",
)


class ContentTranslation(Base):
    __tablename__ = "content_translations"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "locale",
            "field_key",
            name="uq_content_translations_entity_locale_field",
        ),
        Index("ix_content_translations_lookup", "entity_type", "entity_id", "locale"),
        Index("ix_content_translations_source", "source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="tmdb")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
