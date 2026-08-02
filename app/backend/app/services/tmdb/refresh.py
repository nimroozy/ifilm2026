"""Refresh helpers for TMDB demo-owned rows only."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.tmdb.client import TMDBClient
from app.services.tmdb.import_service import ImportResult, refresh_demo_metadata


def refresh_real_demo_metadata(
    db: Session,
    settings: Settings,
    *,
    client: TMDBClient | None = None,
    force: bool = False,
) -> list[ImportResult]:
    return refresh_demo_metadata(db, settings, client=client, force=force)
