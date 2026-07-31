"""Admin publishing workflow routes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import DbSession, require_permissions
from app.models.admin import AdminUser
from app.schemas.publication import (
    PublicationActionOut,
    PublicationActionRequest,
    PublicationEventOut,
    PublicationReadinessOut,
    ReadinessIssueOut,
    SchedulePublicationRequest,
)
from app.services.publishing import workflow as wf
from app.services.publishing.readiness import assess_readiness

router = APIRouter(prefix="/admin/catalog", tags=["publishing"])

EntityTypePath = Literal["movie", "series", "season", "episode"]


def _readiness_out(db: Session, entity_type: str, entity) -> PublicationReadinessOut:
    readiness = assess_readiness(db, entity_type, entity, for_publish=True)
    return PublicationReadinessOut(
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_id=entity.id,
        status=entity.status,
        ready=readiness.ready,
        playable=readiness.playable,
        active_package_id=readiness.active_package_id,
        package_status=readiness.package_status,
        issues=[ReadinessIssueOut(code=i.code, message=i.message, field=i.field) for i in readiness.issues],
        allowed_actions=wf.allowed_actions(entity),
        submitted_for_review_at=getattr(entity, "submitted_for_review_at", None),
        submitted_for_review_by=getattr(entity, "submitted_for_review_by", None),
        approved_at=getattr(entity, "approved_at", None),
        approved_by=getattr(entity, "approved_by", None),
        published_at=getattr(entity, "published_at", None),
        published_by=getattr(entity, "published_by", None),
        scheduled_publish_at=getattr(entity, "scheduled_publish_at", None),
        unpublished_at=getattr(entity, "unpublished_at", None),
        unpublished_by=getattr(entity, "unpublished_by", None),
        archived_at=getattr(entity, "archived_at", None),
        archived_by=getattr(entity, "archived_by", None),
        publication_version=int(getattr(entity, "publication_version", 0) or 0),
    )


def _action_out(entity_type: str, entity) -> PublicationActionOut:
    return PublicationActionOut(
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_id=entity.id,
        status=entity.status,
        scheduled_publish_at=getattr(entity, "scheduled_publish_at", None),
        publication_version=int(getattr(entity, "publication_version", 0) or 0),
    )


@router.get("/{entity_type}/{entity_id}/publication-readiness", response_model=PublicationReadinessOut)
def publication_readiness(
    entity_type: EntityTypePath,
    entity_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("catalog.read"))],
) -> PublicationReadinessOut:
    try:
        entity = wf.get_entity(db, entity_type, entity_id)
    except wf.PublishingWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return _readiness_out(db, entity_type, entity)


@router.get("/{entity_type}/{entity_id}/publication-history", response_model=list[PublicationEventOut])
def publication_history(
    entity_type: EntityTypePath,
    entity_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("catalog.read"))],
) -> list[PublicationEventOut]:
    try:
        wf.get_entity(db, entity_type, entity_id)
    except wf.PublishingWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    events = wf.list_history(db, entity_type=entity_type, entity_id=entity_id)
    return [
        PublicationEventOut(
            id=e.id,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            from_status=e.from_status,
            to_status=e.to_status,
            actor_user_id=e.actor_user_id,
            reason=e.reason,
            event_type=e.event_type,
            metadata_json=e.metadata_json,
            created_at=e.created_at,
        )
        for e in events
    ]


@router.post("/{entity_type}/{entity_id}/submit-review", response_model=PublicationActionOut)
def submit_review(
    entity_type: EntityTypePath,
    entity_id: int,
    payload: PublicationActionRequest,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("catalog.review"))],
) -> PublicationActionOut:
    entity = wf.workflow_http(
        wf.submit_for_review, db, entity_type=entity_type, entity_id=entity_id, actor=admin, reason=payload.reason
    )
    db.commit()
    return _action_out(entity_type, entity)


@router.post("/{entity_type}/{entity_id}/approve", response_model=PublicationActionOut)
def approve(
    entity_type: EntityTypePath,
    entity_id: int,
    payload: PublicationActionRequest,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("catalog.approve"))],
) -> PublicationActionOut:
    entity = wf.workflow_http(
        wf.approve, db, entity_type=entity_type, entity_id=entity_id, actor=admin, reason=payload.reason
    )
    db.commit()
    return _action_out(entity_type, entity)


@router.post("/{entity_type}/{entity_id}/publish", response_model=PublicationActionOut)
def publish(
    entity_type: EntityTypePath,
    entity_id: int,
    payload: PublicationActionRequest,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("catalog.publish"))],
) -> PublicationActionOut:
    entity = wf.workflow_http(
        wf.publish, db, entity_type=entity_type, entity_id=entity_id, actor=admin, reason=payload.reason
    )
    db.commit()
    return _action_out(entity_type, entity)


@router.post("/{entity_type}/{entity_id}/schedule", response_model=PublicationActionOut)
def schedule(
    entity_type: EntityTypePath,
    entity_id: int,
    payload: SchedulePublicationRequest,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("catalog.publish"))],
) -> PublicationActionOut:
    entity = wf.workflow_http(
        wf.schedule,
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=admin,
        scheduled_publish_at=payload.scheduled_publish_at,
        reason=payload.reason,
    )
    db.commit()
    return _action_out(entity_type, entity)


@router.post("/{entity_type}/{entity_id}/unpublish", response_model=PublicationActionOut)
def unpublish(
    entity_type: EntityTypePath,
    entity_id: int,
    payload: PublicationActionRequest,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("catalog.publish"))],
) -> PublicationActionOut:
    entity = wf.workflow_http(
        wf.unpublish, db, entity_type=entity_type, entity_id=entity_id, actor=admin, reason=payload.reason
    )
    db.commit()
    return _action_out(entity_type, entity)


@router.post("/{entity_type}/{entity_id}/archive", response_model=PublicationActionOut)
def archive(
    entity_type: EntityTypePath,
    entity_id: int,
    payload: PublicationActionRequest,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("catalog.archive"))],
) -> PublicationActionOut:
    entity = wf.workflow_http(
        wf.archive, db, entity_type=entity_type, entity_id=entity_id, actor=admin, reason=payload.reason
    )
    db.commit()
    return _action_out(entity_type, entity)
