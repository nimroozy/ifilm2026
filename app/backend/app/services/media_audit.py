"""Structured audit events for media admin mutations."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.media_admin_events import MediaAdminEvent
from app.models.media_assets import new_uuid, utcnow

logger = logging.getLogger("app.media_audit")


def record_media_event(
    db: Session,
    *,
    event_type: str,
    admin_id: int | None,
    media_asset_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> MediaAdminEvent:
    safe = {
        k: v
        for k, v in (details or {}).items()
        if k not in {"token", "shared_secret", "password", "absolute_path"}
    }
    row = MediaAdminEvent(
        id=new_uuid(),
        event_type=event_type,
        media_asset_id=media_asset_id,
        admin_id=admin_id,
        details=safe,
        created_at=utcnow(),
    )
    db.add(row)
    logger.info(
        "media_audit event=%s asset=%s admin=%s details=%s",
        event_type,
        media_asset_id,
        admin_id,
        safe,
    )
    return row
