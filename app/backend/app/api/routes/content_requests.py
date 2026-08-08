"""Subscriber content requests + admin review queue."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.core.deps import CurrentSubscriber, DbSession, require_permissions
from app.models.admin import AdminUser
from app.schemas.common import Envelope, paginated
from app.schemas.content_requests import (
    ContentRequestAdminActionIn,
    ContentRequestAdminListOut,
    ContentRequestAdminOut,
    ContentRequestCreateIn,
    ContentRequestCreateOut,
    ContentRequestEventOut,
    ContentRequestOut,
)
from app.services import content_requests as cr

router = APIRouter(tags=["content-requests"])


@router.post("/me/content-requests", response_model=ContentRequestCreateOut)
def create_my_content_request(
    payload: ContentRequestCreateIn,
    db: DbSession,
    user: CurrentSubscriber,
) -> ContentRequestCreateOut:
    result = cr.create_request(db, user, payload.model_dump())
    db.commit()
    return ContentRequestCreateOut.model_validate(result)


@router.get("/me/content-requests", response_model=Envelope[ContentRequestOut])
def list_my_content_requests(
    db: DbSession,
    user: CurrentSubscriber,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
) -> Envelope[ContentRequestOut]:
    items, total = cr.list_for_subscriber(db, user, page=page, page_size=page_size)
    return paginated(
        [ContentRequestOut.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/me/content-requests/{request_id}", response_model=ContentRequestOut)
def get_my_content_request(
    request_id: int,
    db: DbSession,
    user: CurrentSubscriber,
) -> ContentRequestOut:
    return ContentRequestOut.model_validate(cr.get_for_subscriber(db, user, request_id))


@router.delete("/me/content-requests/{request_id}", response_model=ContentRequestOut)
def withdraw_my_content_request(
    request_id: int,
    db: DbSession,
    user: CurrentSubscriber,
) -> ContentRequestOut:
    out = cr.withdraw(db, user, request_id)
    db.commit()
    return ContentRequestOut.model_validate(out)


@router.get("/admin/content-requests", response_model=ContentRequestAdminListOut)
def admin_list_content_requests(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("content_requests.read"))],
    status: str | None = Query(None, alias="status"),
    request_type: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ContentRequestAdminListOut:
    payload = cr.admin_list(
        db,
        status_filter=status,
        request_type=request_type,
        q=q,
        page=page,
        page_size=page_size,
    )
    return ContentRequestAdminListOut.model_validate(payload)


@router.get("/admin/content-requests/aggregates")
def admin_content_request_aggregates(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("content_requests.read"))],
    limit: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    return {"aggregates": cr.aggregate_demand(db, limit=limit)}


@router.get("/admin/content-requests/{request_id}")
def admin_get_content_request(
    request_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("content_requests.read"))],
) -> dict[str, Any]:
    payload = cr.admin_get(db, request_id)
    return {
        "request": ContentRequestAdminOut.model_validate(payload["request"]),
        "events": [ContentRequestEventOut.model_validate(e) for e in payload["events"]],
    }


@router.post("/admin/content-requests/{request_id}/actions", response_model=ContentRequestAdminOut)
def admin_content_request_action(
    request_id: int,
    payload: ContentRequestAdminActionIn,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("content_requests.manage"))],
) -> ContentRequestAdminOut:
    out = cr.admin_transition(
        db,
        admin,
        request_id,
        action=payload.action,
        admin_note=payload.admin_note,
        public_response=payload.public_response,
        linked_movie_id=payload.linked_movie_id,
        linked_series_id=payload.linked_series_id,
    )
    db.commit()
    return ContentRequestAdminOut.model_validate(out)
