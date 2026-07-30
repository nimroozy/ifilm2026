from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_title: Mapped[str] = mapped_column(String(255), default="")
    year: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    age_rating: Mapped[str] = mapped_column(String(32), default="PG")
    genres: Mapped[list] = mapped_column(JSON, default=list)
    country: Mapped[str] = mapped_column(String(100), default="")
    language: Mapped[str] = mapped_column(String(100), default="")
    director: Mapped[str] = mapped_column(String(255), default="")
    cast: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    poster: Mapped[str] = mapped_column(String(1024), default="")
    backdrop: Mapped[str] = mapped_column(String(1024), default="")
    audio: Mapped[list] = mapped_column(JSON, default=list)
    subtitles: Mapped[list] = mapped_column(JSON, default=list)
    qualities: Mapped[list] = mapped_column(JSON, default=list)
    dubbed: Mapped[list] = mapped_column(JSON, default=list)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    views: Mapped[int] = mapped_column(Integer, default=0)
    hls_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_title: Mapped[str] = mapped_column(String(255), default="")
    year: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    age_rating: Mapped[str] = mapped_column(String(32), default="PG")
    genres: Mapped[list] = mapped_column(JSON, default=list)
    country: Mapped[str] = mapped_column(String(100), default="")
    language: Mapped[str] = mapped_column(String(100), default="")
    seasons: Mapped[int] = mapped_column(Integer, default=1)
    episode_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="Ongoing")
    description: Mapped[str] = mapped_column(Text, default="")
    poster: Mapped[str] = mapped_column(String(1024), default="")
    backdrop: Mapped[str] = mapped_column(String(1024), default="")
    audio: Mapped[list] = mapped_column(JSON, default=list)
    subtitles: Mapped[list] = mapped_column(JSON, default=list)
    dubbed: Mapped[list] = mapped_column(JSON, default=list)
    new_episode: Mapped[bool] = mapped_column(Boolean, default=False)
    views: Mapped[int] = mapped_column(Integer, default=0)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    episodes = relationship("Episode", back_populates="series", cascade="all, delete-orphan")


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    season: Mapped[int] = mapped_column(Integer, default=1)
    episode: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    duration: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    thumbnail: Mapped[str] = mapped_column(String(1024), default="")
    hls_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    series = relationship("Series", back_populates="episodes")
