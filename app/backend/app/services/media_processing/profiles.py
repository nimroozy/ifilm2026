"""Encoding profile selection — never upscale beyond source height."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.media_encoding import MediaEncodingProfile


def list_enabled_profiles(db: Session) -> list[MediaEncodingProfile]:
    return (
        db.query(MediaEncodingProfile)
        .filter(MediaEncodingProfile.enabled.is_(True))
        .order_by(MediaEncodingProfile.sort_order.asc(), MediaEncodingProfile.height.asc())
        .all()
    )


def select_profiles_for_source(
    db: Session,
    *,
    settings: Settings,
    source_height: int,
) -> list[MediaEncodingProfile]:
    """Return enabled profiles at or below source height and HLS_MAX_HEIGHT."""
    if source_height <= 0:
        return []
    max_height = min(int(source_height), int(settings.hls_max_height))
    profiles = list_enabled_profiles(db)
    selected = [p for p in profiles if int(p.height) <= max_height]
    return selected


def even_width_for_height(source_width: int, source_height: int, target_height: int) -> int:
    """Compute even width preserving aspect ratio for a target height (no upscale)."""
    if source_height <= 0 or target_height <= 0:
        return 0
    height = min(target_height, source_height)
    width = int(round(source_width * (height / source_height)))
    if width % 2:
        width -= 1
    return max(2, width)
