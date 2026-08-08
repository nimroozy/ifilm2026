"""Centralized publishing workflow service.

All publication status transitions must go through this module.
Routes must not mutate status fields directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.admin import AdminUser
from app.models.content import Episode, Movie, Season, Series
from app.models.enums import ENTITY_TYPES, PUBLICATION_STATUSES
from app.models.publication import MediaPublicationEvent
from app.services.publishing.readiness import ReadinessResult, assess_readiness
from app.services.streaming.sessions import revoke_sessions_for_asset

ENTITY_MODELS: dict[str, type] = {
    "movie": Movie,
    "series": Series,
    "season": Season,
    "episode": Episode,
}

# Transition matrix: from_status -> allowed to_status values
TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"in_review", "archived"}),
    "in_review": frozenset({"approved", "draft", "archived"}),
    "approved": frozenset({"published", "scheduled", "archived"}),
    "scheduled": frozenset({"published", "unpublished", "archived", "approved"}),
    "published": frozenset({"unpublished", "archived"}),
    "unpublished": frozenset({"published", "archived", "scheduled"}),
    "archived": frozenset(),
}

# Transitions that require publish readiness (active package etc.)
PUBLISH_TARGETS = frozenset({"published", "scheduled"})


def utcnow() -> datetime:
    return datetime.now(UTC)


class PublishingWorkflowError(Exception):
    def __init__(self, message: str, *, code: str = "workflow_error", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def _http_from_workflow(exc: PublishingWorkflowError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def get_entity(db: Session, entity_type: str, entity_id: int, *, for_update: bool = False) -> Any:
    if entity_type not in ENTITY_TYPES:
        raise PublishingWorkflowError("Unknown entity type", code="unknown_entity", status_code=404)
    model: Any = ENTITY_MODELS[entity_type]
    query: Any = db.query(model).filter(model.id == entity_id)
    if for_update:
        query = query.with_for_update()
    entity = query.first()
    if entity is None:
        raise PublishingWorkflowError(f"{entity_type} not found", code="not_found", status_code=404)
    return entity


def _record_event(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    from_status: str,
    to_status: str,
    actor: AdminUser | None,
    reason: str | None,
    event_type: str,
    metadata: dict[str, Any] | None = None,
) -> MediaPublicationEvent:
    event = MediaPublicationEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor.id if actor else None,
        reason=reason,
        event_type=event_type,
        metadata_json=metadata,
        created_at=utcnow(),
    )
    db.add(event)
    return event


def _assert_transition(current: str, target: str) -> None:
    if current not in PUBLICATION_STATUSES:
        raise PublishingWorkflowError(f"Unknown current status: {current}", code="invalid_status")
    allowed = TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise PublishingWorkflowError(
            f"Cannot transition from {current} to {target}",
            code="invalid_transition",
        )


def _revoke_playback_for_entity(db: Session, entity_type: str, entity) -> None:
    """Revoke active playback sessions when content leaves the public catalog."""
    from app.models.media_assets import MediaAsset

    assets: list[MediaAsset] = []
    if entity_type == "movie":
        assets = db.query(MediaAsset).filter(MediaAsset.movie_id == entity.id).all()
    elif entity_type == "episode":
        assets = db.query(MediaAsset).filter(MediaAsset.episode_id == entity.id).all()
    for asset in assets:
        try:
            revoke_sessions_for_asset(db, media_asset_id=asset.id, reason="catalog_unpublished")
        except Exception:
            # Best-effort; visibility recheck also protects delivery.
            pass


def _apply_status_side_effects(
    entity,
    *,
    from_status: str,
    to_status: str,
    actor: AdminUser | None,
    reason: str | None,
    scheduled_publish_at: datetime | None,
) -> None:
    now = utcnow()
    actor_id = actor.id if actor else None
    entity.status = to_status
    entity.publication_reason = reason
    entity.publication_version = int(getattr(entity, "publication_version", 0) or 0) + 1
    entity.updated_at = now

    if to_status == "in_review":
        entity.submitted_for_review_at = now
        entity.submitted_for_review_by = actor_id
    elif to_status == "approved":
        entity.approved_at = now
        entity.approved_by = actor_id
        entity.scheduled_publish_at = None
    elif to_status == "scheduled":
        entity.scheduled_publish_at = scheduled_publish_at
    elif to_status == "published":
        entity.published_at = entity.published_at or now
        entity.published_by = actor_id
        entity.scheduled_publish_at = None
        entity.unpublished_at = None
        entity.unpublished_by = None
        entity.deleted_at = None
        entity.archived_at = None
        entity.archived_by = None
    elif to_status == "unpublished":
        entity.unpublished_at = now
        entity.unpublished_by = actor_id
        entity.scheduled_publish_at = None
    elif to_status == "archived":
        entity.archived_at = now
        entity.archived_by = actor_id
        entity.deleted_at = entity.deleted_at or now
        entity.scheduled_publish_at = None
    elif to_status == "draft" and from_status == "in_review":
        # Reject back to draft — clear review stamps optionally keep history in events.
        entity.scheduled_publish_at = None


def transition(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    to_status: str,
    actor: AdminUser | None,
    reason: str | None = None,
    scheduled_publish_at: datetime | None = None,
    event_type: str | None = None,
    skip_readiness: bool = False,
    metadata: dict[str, Any] | None = None,
):
    entity = get_entity(db, entity_type, entity_id, for_update=True)
    from_status = entity.status
    _assert_transition(from_status, to_status)

    if to_status == "scheduled":
        if scheduled_publish_at is None:
            raise PublishingWorkflowError(
                "scheduled_publish_at is required",
                code="missing_schedule",
            )
        if scheduled_publish_at.tzinfo is None:
            raise PublishingWorkflowError(
                "scheduled_publish_at must be timezone-aware UTC",
                code="invalid_schedule",
            )
        aware = scheduled_publish_at.astimezone(UTC)
        if aware <= utcnow():
            raise PublishingWorkflowError(
                "scheduled_publish_at must be in the future",
                code="schedule_not_future",
            )
        scheduled_publish_at = aware

    readiness: ReadinessResult | None = None
    if to_status in PUBLISH_TARGETS and not skip_readiness:
        readiness = assess_readiness(db, entity_type, entity, for_publish=True)
        if not readiness.ready:
            _record_event(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                from_status=from_status,
                to_status=from_status,
                actor=actor,
                reason=reason,
                event_type="readiness_check_failed",
                metadata={
                    "target": to_status,
                    "issues": [{"code": i.code, "message": i.message, "field": i.field} for i in readiness.issues],
                },
            )
            db.flush()
            raise PublishingWorkflowError(
                "Content is not ready for publication",
                code="not_ready",
                status_code=409,
            )

    _apply_status_side_effects(
        entity,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        reason=reason,
        scheduled_publish_at=scheduled_publish_at,
    )
    resolved_event = event_type or {
        "in_review": "review_submitted",
        "approved": "approval_granted",
        "scheduled": "publication_scheduled",
        "published": "publication_executed",
        "unpublished": "unpublished",
        "archived": "archived",
        "draft": "review_rejected",
    }.get(to_status, "transition")

    _record_event(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        reason=reason,
        event_type=resolved_event,
        metadata=metadata
        or (
            {
                "playable": readiness.playable if readiness else None,
                "active_package_id": readiness.active_package_id if readiness else None,
            }
            if readiness
            else None
        ),
    )

    if to_status in {"unpublished", "archived"} and from_status == "published":
        _revoke_playback_for_entity(db, entity_type, entity)

    db.add(entity)
    db.flush()
    return entity


def submit_for_review(db: Session, *, entity_type: str, entity_id: int, actor: AdminUser, reason: str | None = None):
    return transition(db, entity_type=entity_type, entity_id=entity_id, to_status="in_review", actor=actor, reason=reason)


def approve(db: Session, *, entity_type: str, entity_id: int, actor: AdminUser, reason: str | None = None):
    return transition(db, entity_type=entity_type, entity_id=entity_id, to_status="approved", actor=actor, reason=reason)


def reject_review(db: Session, *, entity_type: str, entity_id: int, actor: AdminUser, reason: str | None = None):
    return transition(db, entity_type=entity_type, entity_id=entity_id, to_status="draft", actor=actor, reason=reason)


def publish(db: Session, *, entity_type: str, entity_id: int, actor: AdminUser | None, reason: str | None = None):
    entity = get_entity(db, entity_type, entity_id, for_update=True)
    # Allow approved → published and unpublished → published
    if entity.status == "scheduled":
        result = transition(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            to_status="published",
            actor=actor,
            reason=reason,
            event_type="publication_executed",
        )
    else:
        result = transition(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            to_status="published",
            actor=actor,
            reason=reason,
            event_type="publication_executed",
        )
    from app.services.recommendations.cache import bump_catalog_feature_epoch

    bump_catalog_feature_epoch()
    return result


def schedule(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    actor: AdminUser,
    scheduled_publish_at: datetime,
    reason: str | None = None,
):
    entity = get_entity(db, entity_type, entity_id, for_update=True)
    # unpublished → scheduled is allowed by matrix; approved → scheduled too.
    if entity.status == "scheduled":
        # Reschedule: briefly move to approved then scheduled, or update in place via approved.
        transition(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            to_status="approved",
            actor=actor,
            reason=reason or "reschedule",
            event_type="schedule_cancelled",
            skip_readiness=True,
        )
    return transition(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        to_status="scheduled",
        actor=actor,
        reason=reason,
        scheduled_publish_at=scheduled_publish_at,
        event_type="publication_scheduled",
    )


def unpublish(db: Session, *, entity_type: str, entity_id: int, actor: AdminUser, reason: str | None = None):
    entity = get_entity(db, entity_type, entity_id, for_update=True)
    if entity.status == "scheduled":
        # Cancel schedule → unpublished (or approved). Spec: scheduled → unpublished.
        return transition(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            to_status="unpublished",
            actor=actor,
            reason=reason or "schedule_cancelled",
            event_type="unpublished",
            skip_readiness=True,
        )
    return transition(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        to_status="unpublished",
        actor=actor,
        reason=reason,
    )


def archive(db: Session, *, entity_type: str, entity_id: int, actor: AdminUser, reason: str | None = None):
    return transition(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        to_status="archived",
        actor=actor,
        reason=reason,
        skip_readiness=True,
    )


def list_history(db: Session, *, entity_type: str, entity_id: int, limit: int = 100) -> list[MediaPublicationEvent]:
    return (
        db.query(MediaPublicationEvent)
        .filter(
            MediaPublicationEvent.entity_type == entity_type,
            MediaPublicationEvent.entity_id == entity_id,
        )
        .order_by(MediaPublicationEvent.created_at.desc(), MediaPublicationEvent.id.desc())
        .limit(limit)
        .all()
    )


def allowed_actions(entity) -> list[str]:
    current = entity.status
    targets = TRANSITIONS.get(current, frozenset())
    actions: list[str] = []
    mapping = {
        "in_review": "submit_review",
        "approved": "approve",
        "draft": "reject",
        "published": "publish",
        "scheduled": "schedule",
        "unpublished": "unpublish",
        "archived": "archive",
    }
    for target in sorted(targets):
        actions.append(mapping.get(target, target))
    # Explicit aliases for UI
    if "in_review" in targets:
        actions.append("submit_review")
    if "approved" in targets and current == "in_review":
        actions.append("approve")
    if "draft" in targets and current == "in_review":
        actions.append("reject")
    if "published" in targets:
        actions.append("publish")
    if "scheduled" in targets:
        actions.append("schedule")
    if "unpublished" in targets:
        actions.append("unpublish")
    if "archived" in targets:
        actions.append("archive")
    # Dedupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for action in actions:
        if action not in seen:
            seen.add(action)
            ordered.append(action)
    return ordered


def workflow_http(fn, *args, **kwargs):
    """Call a workflow function and convert PublishingWorkflowError to HTTPException."""
    try:
        return fn(*args, **kwargs)
    except PublishingWorkflowError as exc:
        raise _http_from_workflow(exc) from exc
