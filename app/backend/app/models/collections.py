"""Curated content collections (Collections V1)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


COLLECTION_TYPES = (
    "editorial",
    "franchise",
    "seasonal",
    "genre_feature",
    "regional",
    "language",
    "staff_pick",
)

COLLECTION_STATUSES = ("draft", "published", "archived")


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("slug", name="uq_collections_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(280), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    short_description: Mapped[str] = mapped_column(String(500), default="")
    collection_type: Mapped[str] = mapped_column(String(32), default="editorial", index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    visibility: Mapped[str] = mapped_column(String(32), default="public", index=True)
    poster_url: Mapped[str] = mapped_column(String(1024), default="")
    backdrop_url: Mapped[str] = mapped_column(String(1024), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    demo_owned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    demo_seed_version: Mapped[str] = mapped_column(String(32), default="")
    created_by_admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    items: Mapped[list[CollectionItem]] = relationship(
        "CollectionItem",
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="CollectionItem.position",
    )


class CollectionItem(Base):
    __tablename__ = "collection_items"
    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL AND series_id IS NULL) OR (movie_id IS NULL AND series_id IS NOT NULL)",
            name="ck_collection_items_one_owner",
        ),
        UniqueConstraint("collection_id", "position", name="uq_collection_items_position"),
        Index(
            "uq_collection_items_movie",
            "collection_id",
            "movie_id",
            unique=True,
            sqlite_where=text("movie_id IS NOT NULL"),
            postgresql_where=text("movie_id IS NOT NULL"),
        ),
        Index(
            "uq_collection_items_series",
            "collection_id",
            "series_id",
            unique=True,
            sqlite_where=text("series_id IS NOT NULL"),
            postgresql_where=text("series_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movie_id: Mapped[int | None] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    custom_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    custom_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by_admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    collection: Mapped[Collection] = relationship("Collection", back_populates="items")
    movie = relationship("Movie")
    series = relationship("Series")
