"""Public and admin schemas for content requests (no private admin note leakage)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

RequestType = Literal["movie", "series"]
RequestStatus = Literal["new", "reviewing", "approved", "rejected", "added", "withdrawn"]
AdminAction = Literal["review", "approve", "reject", "mark_added", "reopen"]


class ContentRequestCreateIn(BaseModel):
    request_type: RequestType
    title: str = Field(min_length=1, max_length=255)
    year: int | None = Field(default=None, ge=1870, le=2100)
    tmdb_url: str | None = Field(default=None, max_length=512)
    imdb_url: str | None = Field(default=None, max_length=512)
    tmdb_id: int | None = Field(default=None, ge=1)
    imdb_id: str | None = Field(default=None, max_length=32)
    preferred_language: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)
    # When true and only a fuzzy catalog match exists, allow creating the request.
    force: bool = False

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("title is required")
        return cleaned

    @field_validator("notes", "preferred_language", "tmdb_url", "imdb_url", "imdb_id")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class CatalogMatchOut(BaseModel):
    content_type: RequestType
    id: int
    slug: str
    title: str
    release_year: int | None = None
    poster_url: str = ""
    detail_path: str
    match_strength: Literal["exact", "likely"] = "exact"
    match_reason: str = ""


class ContentRequestOut(BaseModel):
    id: int
    request_type: RequestType
    title: str
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    tmdb_url: str | None = None
    imdb_url: str | None = None
    preferred_language: str | None = None
    notes: str | None = None
    status: RequestStatus
    public_response: str | None = None
    linked_movie_id: int | None = None
    linked_series_id: int | None = None
    linked_detail_path: str | None = None
    linked_title: str | None = None
    demand_count: int = 1
    created_at: str
    updated_at: str
    reviewed_at: str | None = None


class ContentRequestCreateOut(BaseModel):
    """Create response — either a new/existing request or an already-available catalog hit."""

    outcome: Literal["created", "existing_request", "already_available", "suggestions"]
    message: str
    request: ContentRequestOut | None = None
    catalog_item: CatalogMatchOut | None = None
    suggestions: list[CatalogMatchOut] = Field(default_factory=list)


class ContentRequestAdminOut(ContentRequestOut):
    subscriber_id: int
    subscriber_username: str | None = None
    admin_note: str | None = None
    reviewed_by_admin_id: int | None = None
    normalized_title: str = ""


class ContentRequestEventOut(BaseModel):
    id: int
    event_type: str
    from_status: str | None = None
    to_status: str | None = None
    actor_admin_id: int | None = None
    actor_subscriber_id: int | None = None
    detail: str | None = None
    created_at: str


class ContentRequestAdminActionIn(BaseModel):
    action: AdminAction
    admin_note: str | None = Field(default=None, max_length=4000)
    public_response: str | None = Field(default=None, max_length=512)
    linked_movie_id: int | None = None
    linked_series_id: int | None = None

    @model_validator(mode="after")
    def validate_link(self) -> ContentRequestAdminActionIn:
        if self.linked_movie_id is not None and self.linked_series_id is not None:
            raise ValueError("Provide at most one linked catalog item")
        if self.action == "mark_added" and self.linked_movie_id is None and self.linked_series_id is None:
            raise ValueError("mark_added requires linked_movie_id or linked_series_id")
        return self


class AggregateDemandOut(BaseModel):
    request_type: RequestType
    title: str
    normalized_title: str
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    request_count: int
    open_count: int
    preferred_languages: dict[str, int] = Field(default_factory=dict)
    latest_requested_at: str | None = None


class ContentRequestAdminListOut(BaseModel):
    items: list[ContentRequestAdminOut]
    total: int
    page: int
    page_size: int
    aggregates: list[AggregateDemandOut] = Field(default_factory=list)
