"""Schemas for curated content collections (Collections V1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.collections import COLLECTION_STATUSES, COLLECTION_TYPES
from app.schemas.common import ORMModel
from app.schemas.content import MovieOut, SeriesOut
from app.utils.slug import normalize_slug

CollectionType = Literal[
    "editorial",
    "franchise",
    "seasonal",
    "genre_feature",
    "regional",
    "language",
    "staff_pick",
]
CollectionStatus = Literal["draft", "published", "archived"]
CollectionVisibility = Literal["public", "unlisted"]


def _trim(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def _validate_http_url(value: str) -> str:
    if not value:
        return value
    if ".." in value or value.startswith("file:"):
        raise ValueError("Invalid artwork URL")
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError("URL must start with http:// or https://")
    return value


class CollectionCreate(BaseModel):
    title: str
    slug: str | None = None
    description: str = ""
    short_description: str = ""
    collection_type: CollectionType = "editorial"
    visibility: CollectionVisibility = "public"
    poster_url: str = ""
    backdrop_url: str = ""
    sort_order: int = 0
    is_featured: bool = False

    @field_validator("title", "description", "short_description", "poster_url", "backdrop_url", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return _trim(value)

    @field_validator("title")
    @classmethod
    def title_required(cls, value: str) -> str:
        if not value:
            raise ValueError("title must not be empty")
        return value

    @field_validator("collection_type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value not in COLLECTION_TYPES:
            raise ValueError(f"collection_type must be one of {COLLECTION_TYPES}")
        return value

    @field_validator("poster_url", "backdrop_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _validate_http_url(value)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        normalized = normalize_slug(value)
        if not normalized:
            raise ValueError("slug is invalid")
        return normalized

    @field_validator("short_description")
    @classmethod
    def short_len(cls, value: str) -> str:
        if len(value) > 500:
            raise ValueError("short_description must be at most 500 characters")
        return value


class CollectionUpdate(BaseModel):
    title: str | None = None
    slug: str | None = None
    description: str | None = None
    short_description: str | None = None
    collection_type: CollectionType | None = None
    visibility: CollectionVisibility | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    sort_order: int | None = None
    is_featured: bool | None = None
    expected_updated_at: datetime | None = None

    @field_validator(
        "title",
        "slug",
        "description",
        "short_description",
        "poster_url",
        "backdrop_url",
        mode="before",
    )
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return _trim(value)

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("title must not be empty")
        return value

    @field_validator("collection_type")
    @classmethod
    def validate_type(cls, value: str | None) -> str | None:
        if value is not None and value not in COLLECTION_TYPES:
            raise ValueError(f"collection_type must be one of {COLLECTION_TYPES}")
        return value

    @field_validator("poster_url", "backdrop_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_http_url(value)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        normalized = normalize_slug(value)
        if not normalized:
            raise ValueError("slug is invalid")
        return normalized


class CollectionItemAdd(BaseModel):
    movie_id: int | None = None
    series_id: int | None = None
    custom_title: str | None = None
    custom_description: str | None = None
    position: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def one_owner(self) -> CollectionItemAdd:
        has_movie = self.movie_id is not None
        has_series = self.series_id is not None
        if has_movie == has_series:
            raise ValueError("Exactly one of movie_id or series_id is required")
        return self


class CollectionReorder(BaseModel):
    item_ids: list[int] = Field(min_length=1)
    expected_updated_at: datetime | None = None


class CollectionItemOut(ORMModel):
    id: int
    collection_id: int
    movie_id: int | None = None
    series_id: int | None = None
    position: int
    custom_title: str | None = None
    custom_description: str | None = None
    content_type: Literal["movie", "series"]
    movie: MovieOut | None = None
    series: SeriesOut | None = None
    created_at: datetime | None = None
    publicly_visible: bool = True


class CollectionOut(ORMModel):
    id: int
    title: str
    slug: str
    description: str = ""
    short_description: str = ""
    collection_type: str
    status: str
    visibility: str
    poster_url: str = ""
    backdrop_url: str = ""
    sort_order: int = 0
    is_featured: bool = False
    demo_owned: bool = False
    demo_seed_version: str = ""
    item_count: int = 0
    visible_item_count: int = 0
    items: list[CollectionItemOut] = Field(default_factory=list)
    created_by_admin_id: int | None = None
    updated_by_admin_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    published_at: datetime | None = None
    archived_at: datetime | None = None


class CollectionPublicOut(BaseModel):
    """Public-safe collection payload — no admin/audit/demo internals."""

    id: int
    title: str
    slug: str
    description: str = ""
    short_description: str = ""
    collection_type: str
    poster_url: str = ""
    backdrop_url: str = ""
    sort_order: int = 0
    is_featured: bool = False
    item_count: int = 0
    items: list[CollectionItemOut] = Field(default_factory=list)
    published_at: datetime | None = None


class CollectionStatusAction(BaseModel):
    """Optional body for publish/unpublish/archive."""

    expected_updated_at: datetime | None = None


# Keep status constants importable for OpenAPI / tests.
assert set(COLLECTION_STATUSES) >= {"draft", "published", "archived"}
