"""Scheduled publishing worker — claim due scheduled items and publish."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.content import Episode, Movie, Season, Series
from app.models.publication import MediaPublicationEvent
from app.services.publishing.readiness import assess_readiness
from app.services.publishing.workflow import PublishingWorkflowError, transition, utcnow

logger = logging.getLogger(__name__)

_SCHEDULED_MODELS: list[tuple[str, type]] = [
    ("movie", Movie),
    ("series", Series),
    ("season", Season),
    ("episode", Episode),
]


def _due_query(db: Session, model, *, now: datetime):
    q = (
        db.query(model)
        .filter(
            model.status == "scheduled",
            model.deleted_at.is_(None),
            model.scheduled_publish_at.isnot(None),
            model.scheduled_publish_at <= now,
        )
        .order_by(model.scheduled_publish_at.asc(), model.id.asc())
    )
    return q


def claim_due_entity(db: Session) -> tuple[str, object] | None:
    """Atomically claim one due scheduled entity (FOR UPDATE SKIP LOCKED when available)."""
    now = utcnow()
    for entity_type, model in _SCHEDULED_MODELS:
        query = _due_query(db, model, now=now)
        try:
            entity = query.with_for_update(skip_locked=True).first()
        except Exception:
            entity = query.with_for_update().first()
        if entity is not None:
            return entity_type, entity
    return None


def process_due_entity(db: Session, entity_type: str, entity) -> bool:
    """
    Publish one claimed scheduled entity after readiness revalidation.
    Returns True if published, False if left unpublished due to readiness failure.
    Idempotent: if no longer scheduled, no-op.
    """
    # Re-load with lock
    model = type(entity)
    locked = db.query(model).filter(model.id == entity.id).with_for_update().first()
    if locked is None or locked.status != "scheduled":
        return False

    readiness = assess_readiness(db, entity_type, locked, for_publish=True)
    if not readiness.ready:
        db.add(
            MediaPublicationEvent(
                entity_type=entity_type,
                entity_id=locked.id,
                from_status="scheduled",
                to_status="scheduled",
                actor_user_id=None,
                reason="Scheduled publish readiness failed",
                event_type="publication_failed",
                metadata_json={
                    "issues": [
                        {"code": i.code, "message": i.message, "field": i.field} for i in readiness.issues
                    ]
                },
                created_at=utcnow(),
            )
        )
        # Leave scheduled item unpublished: move to approved so it does not retry forever
        # without operator action, while preserving schedule failure history.
        locked.status = "approved"
        locked.scheduled_publish_at = None
        locked.publication_version = int(getattr(locked, "publication_version", 0) or 0) + 1
        locked.updated_at = utcnow()
        db.add(locked)
        db.flush()
        logger.warning(
            "Scheduled publish readiness failed for %s/%s", entity_type, locked.id
        )
        return False

    try:
        transition(
            db,
            entity_type=entity_type,
            entity_id=locked.id,
            to_status="published",
            actor=None,
            reason="scheduled_publish",
            event_type="publication_executed",
            metadata={"source": "scheduler"},
        )
    except PublishingWorkflowError as exc:
        db.add(
            MediaPublicationEvent(
                entity_type=entity_type,
                entity_id=locked.id,
                from_status="scheduled",
                to_status="scheduled",
                actor_user_id=None,
                reason=exc.message,
                event_type="publication_failed",
                metadata_json={"code": exc.code},
                created_at=utcnow(),
            )
        )
        db.flush()
        logger.warning("Scheduled publish failed for %s/%s: %s", entity_type, locked.id, exc.message)
        return False
    return True


def run_once(db: Session) -> bool:
    """Process at most one due scheduled publication. Returns True if work was done."""
    claimed = claim_due_entity(db)
    if claimed is None:
        return False
    entity_type, entity = claimed
    published = process_due_entity(db, entity_type, entity)
    db.commit()
    return published or True  # claimed work counts as processed even on readiness failure


def run_due_batch(db: Session, *, limit: int = 50) -> dict[str, int]:
    """Process up to `limit` due items. Returns counts."""
    published = 0
    failed = 0
    for _ in range(limit):
        claimed = claim_due_entity(db)
        if claimed is None:
            break
        entity_type, entity = claimed
        ok = process_due_entity(db, entity_type, entity)
        if ok:
            published += 1
        else:
            failed += 1
        db.commit()
    return {"published": published, "failed": failed, "processed": published + failed}
