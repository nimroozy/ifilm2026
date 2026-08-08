"""Stored TMDB cast credits for movie/series detail pages."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class MovieCastCredit(Base):
    __tablename__ = "movie_cast_credits"
    __table_args__ = (
        UniqueConstraint("movie_id", "tmdb_person_id", name="uq_movie_cast_credits_person"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), nullable=False, index=True)
    tmdb_person_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    character_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    profile_path: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    profile_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    credit_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SeriesCastCredit(Base):
    __tablename__ = "series_cast_credits"
    __table_args__ = (
        UniqueConstraint("series_id", "tmdb_person_id", name="uq_series_cast_credits_person"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), nullable=False, index=True)
    tmdb_person_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    character_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    profile_path: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    profile_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    credit_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
