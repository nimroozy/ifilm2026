"""Publication workflow API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

EntityType = Literal["movie", "series", "season", "episode"]


class PublicationActionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value


class SchedulePublicationRequest(PublicationActionRequest):
    scheduled_publish_at: datetime

    @field_validator("scheduled_publish_at")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("scheduled_publish_at must include timezone (UTC recommended)")
        return value


class ReadinessIssueOut(BaseModel):
    code: str
    message: str
    field: str | None = None


class PublicationReadinessOut(BaseModel):
    entity_type: EntityType
    entity_id: int
    status: str
    ready: bool
    playable: bool
    active_package_id: str | None = None
    package_status: str | None = None
    issues: list[ReadinessIssueOut] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    submitted_for_review_at: datetime | None = None
    submitted_for_review_by: int | None = None
    approved_at: datetime | None = None
    approved_by: int | None = None
    published_at: datetime | None = None
    published_by: int | None = None
    scheduled_publish_at: datetime | None = None
    unpublished_at: datetime | None = None
    unpublished_by: int | None = None
    archived_at: datetime | None = None
    archived_by: int | None = None
    publication_version: int = 0


class PublicationEventOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    from_status: str
    to_status: str
    actor_user_id: int | None = None
    reason: str | None = None
    event_type: str
    metadata_json: dict[str, Any] | None = None
    created_at: datetime


class PublicationActionOut(BaseModel):
    detail: str = "ok"
    entity_type: EntityType
    entity_id: int
    status: str
    scheduled_publish_at: datetime | None = None
    publication_version: int = 0
