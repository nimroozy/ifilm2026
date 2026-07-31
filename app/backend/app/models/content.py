from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


movie_genres = Table(
    "movie_genres",
    Base.metadata,
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)

series_genres = Table(
    "series_genres",
    Base.metadata,
    Column("series_id", ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    movies = relationship("Movie", secondary=movie_genres, back_populates="genre_links")
    series = relationship("Series", secondary=series_genres, back_populates="genre_links")


class Movie(Base):
    __tablename__ = "movies"
    __table_args__ = (UniqueConstraint("slug", name="uq_movies_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_title: Mapped[str] = mapped_column(String(255), default="")
    slug: Mapped[str] = mapped_column(String(280), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    short_description: Mapped[str] = mapped_column(String(500), default="")
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_rating: Mapped[str] = mapped_column(String(32), default="")
    language: Mapped[str] = mapped_column(String(100), default="", index=True)
    country: Mapped[str] = mapped_column(String(100), default="")
    imdb_id: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    imdb_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    poster_url: Mapped[str] = mapped_column(String(1024), default="")
    backdrop_url: Mapped[str] = mapped_column(String(1024), default="")
    trailer_url: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_trending: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Compatibility / media plumbing (not exposed as binary upload in this milestone)
    director: Mapped[str] = mapped_column(String(255), default="")
    cast: Mapped[list] = mapped_column(JSON, default=list)
    audio: Mapped[list] = mapped_column(JSON, default=list)
    subtitles: Mapped[list] = mapped_column(JSON, default=list)
    qualities: Mapped[list] = mapped_column(JSON, default=list)
    dubbed: Mapped[list] = mapped_column(JSON, default=list)
    views: Mapped[int] = mapped_column(Integer, default=0)
    hls_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    genre_links: Mapped[list[Genre]] = relationship(
        "Genre", secondary=movie_genres, back_populates="movies"
    )


class Series(Base):
    __tablename__ = "series"
    __table_args__ = (UniqueConstraint("slug", name="uq_series_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_title: Mapped[str] = mapped_column(String(255), default="")
    slug: Mapped[str] = mapped_column(String(280), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    short_description: Mapped[str] = mapped_column(String(500), default="")
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    end_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_rating: Mapped[str] = mapped_column(String(32), default="")
    language: Mapped[str] = mapped_column(String(100), default="", index=True)
    country: Mapped[str] = mapped_column(String(100), default="")
    imdb_id: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    imdb_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    poster_url: Mapped[str] = mapped_column(String(1024), default="")
    backdrop_url: Mapped[str] = mapped_column(String(1024), default="")
    trailer_url: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    airing_status: Mapped[str] = mapped_column(String(32), default="Ongoing")
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_trending: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    audio: Mapped[list] = mapped_column(JSON, default=list)
    subtitles: Mapped[list] = mapped_column(JSON, default=list)
    dubbed: Mapped[list] = mapped_column(JSON, default=list)
    new_episode: Mapped[bool] = mapped_column(Boolean, default=False)
    views: Mapped[int] = mapped_column(Integer, default=0)

    genre_links: Mapped[list[Genre]] = relationship(
        "Genre", secondary=series_genres, back_populates="series"
    )
    seasons: Mapped[list[Season]] = relationship(
        "Season",
        back_populates="series",
        cascade="all, delete-orphan",
        order_by="Season.season_number",
    )


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (
        UniqueConstraint("series_id", "season_number", name="uq_season_number_per_series"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    poster_url: Mapped[str] = mapped_column(String(1024), default="")
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    series: Mapped[Series] = relationship("Series", back_populates="seasons")
    episodes: Mapped[list[Episode]] = relationship(
        "Episode",
        back_populates="season",
        cascade="all, delete-orphan",
        order_by="Episode.episode_number",
    )


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint("season_id", "episode_number", name="uq_episode_number_per_season"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    thumbnail_url: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    hls_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    season: Mapped[Season] = relationship("Season", back_populates="episodes")
    series: Mapped[Series] = relationship("Series")
