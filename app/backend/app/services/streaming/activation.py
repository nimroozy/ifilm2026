"""Explicit active HLS package selection and activation."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.media_assets import utcnow
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage
from app.services.media_processing.errors import PermanentProcessingError


class ActivePackageError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def get_active_completed_package(db: Session, media_asset_id: str) -> MediaPackage | None:
    return (
        db.query(MediaPackage)
        .options(joinedload(MediaPackage.renditions))
        .filter(
            MediaPackage.media_asset_id == media_asset_id,
            MediaPackage.package_type == PACKAGE_TYPE_HLS_VOD,
            MediaPackage.status == "completed",
            MediaPackage.is_active.is_(True),
        )
        .one_or_none()
    )


def require_active_completed_package(db: Session, media_asset_id: str) -> MediaPackage:
    package = get_active_completed_package(db, media_asset_id)
    if package is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active completed HLS package for this asset",
        )
    return package


def _assert_package_activatable(db: Session, package: MediaPackage) -> list:
    if package.status != "completed":
        raise ActivePackageError(
            "package_not_completed",
            "Only completed packages can become active",
        )
    if package.package_type != PACKAGE_TYPE_HLS_VOD:
        raise ActivePackageError("unsupported_package_type", "Only HLS VOD packages can be active")
    from app.models.media_encoding import MediaRendition

    renditions = (
        db.query(MediaRendition).filter(MediaRendition.package_id == package.id).all()
    )
    if not renditions:
        raise ActivePackageError("missing_renditions", "Package has no renditions")
    if any(item.status != "completed" for item in renditions):
        raise ActivePackageError("incomplete_renditions", "All renditions must be completed")
    if not package.storage_path or not package.master_playlist_path:
        raise ActivePackageError("missing_paths", "Package storage paths are incomplete")
    return renditions


def activate_completed_package(db: Session, package: MediaPackage) -> MediaPackage:
    """Mark a completed package active; supersede any prior active package atomically.

    Call only after validation + promotion + rendition rows are committed to the
    same unit of work (or flushed). Never activates failed/cancelled/in-flight packages.
    """
    _assert_package_activatable(db, package)

    # Lock all packages for the asset so concurrent activations serialize.
    locked = (
        db.query(MediaPackage)
        .filter(MediaPackage.media_asset_id == package.media_asset_id)
        .with_for_update()
        .all()
    )
    now = utcnow()
    for other in locked:
        if other.id == package.id:
            continue
        if other.is_active:
            other.is_active = False
            other.superseded_at = now
            db.add(other)
    # Flush deactivations before activating so partial unique indexes stay satisfied.
    db.flush()

    package.is_active = True
    package.activated_at = now
    package.superseded_at = None
    db.add(package)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ActivePackageError(
            "active_package_conflict",
            "Another active package already exists for this asset",
        ) from exc
    return package


def activate_or_fail_encode(db: Session, package: MediaPackage) -> None:
    """Worker helper: activation failure fails the encode permanently."""
    try:
        activate_completed_package(db, package)
    except ActivePackageError as exc:
        raise PermanentProcessingError(str(exc), code=exc.code) from exc
