"""Idempotent post-promote sync of HLS packages to central object origin.

Local MEDIA_ROOT copies are never deleted or moved. Sync is flag-gated and
records durable status on ``media_packages``. Transient failures are retryable
via ``media_processing_jobs`` and must not un-activate the local package.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.media_assets import new_uuid, utcnow
from app.models.media_encoding import MediaPackage
from app.models.media_processing import (
    ACTIVE_JOB_STATUSES,
    JOB_TYPE_ORIGIN_SYNC,
    MediaProcessingJob,
)
from app.services.media_processing.jobs import add_job_event
from app.services.object_storage.factory import get_central_origin_storage
from app.services.object_storage.keys import ObjectKeyBuilder
from app.services.object_storage.protocol import ObjectStorage

logger = logging.getLogger(__name__)

ORIGIN_SYNC_STATUS_NONE = "none"
ORIGIN_SYNC_STATUS_PENDING = "pending"
ORIGIN_SYNC_STATUS_SYNCING = "syncing"
ORIGIN_SYNC_STATUS_SYNCED = "synced"
ORIGIN_SYNC_STATUS_FAILED = "failed"

_CLIP_ERROR = 1024


@dataclass(frozen=True)
class PackageSyncResult:
    package_id: str
    object_count: int
    bytes_synced: int
    skipped_existing: int
    object_prefix: str


class OriginSyncError(Exception):
    """Raised when origin sync fails; safe for logs (no secrets)."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def origin_package_sync_enabled(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return bool(cfg.enable_object_storage and cfg.enable_origin_package_sync)


def find_active_origin_sync_job(db: Session, package_id: str) -> MediaProcessingJob | None:
    return (
        db.query(MediaProcessingJob)
        .filter(
            MediaProcessingJob.job_type == JOB_TYPE_ORIGIN_SYNC,
            MediaProcessingJob.target_package_id == package_id,
            MediaProcessingJob.status.in_(tuple(ACTIVE_JOB_STATUSES)),
        )
        .first()
    )


def enqueue_origin_package_sync(
    db: Session,
    *,
    package: MediaPackage,
    settings: Settings | None = None,
    admin_id: int | None = None,
) -> MediaProcessingJob | None:
    """Queue an origin sync job after local promote/activate. No-op when flags are off."""
    cfg = settings or get_settings()
    if not origin_package_sync_enabled(cfg):
        return None
    if package.status != "completed" or not package.is_active:
        return None
    if not package.storage_path or not package.media_asset_id:
        return None

    existing = find_active_origin_sync_job(db, package.id)
    if existing is not None:
        return existing

    if package.origin_sync_status == ORIGIN_SYNC_STATUS_SYNCED and package.origin_object_prefix:
        # Already synced — leave durable state; caller may force re-queue later.
        return None

    package.origin_sync_status = ORIGIN_SYNC_STATUS_PENDING
    package.origin_sync_error = None
    db.add(package)

    job = MediaProcessingJob(
        id=new_uuid(),
        media_asset_id=package.media_asset_id,
        target_package_id=package.id,
        job_type=JOB_TYPE_ORIGIN_SYNC,
        status="queued",
        priority=80,
        attempt_count=0,
        max_attempts=cfg.media_processing_max_attempts,
        progress_percent=0,
        current_step="queued",
        queued_at=utcnow(),
        created_by_admin_id=admin_id,
    )
    try:
        db.add(job)
        db.flush()
        add_job_event(
            db,
            job,
            "queued",
            "Origin package sync queued",
            {"package_id": package.id},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        return find_active_origin_sync_job(db, package.id)
    db.refresh(job)
    logger.info(
        "origin_package_sync_queued",
        extra={"package_id": package.id, "job_id": job.id, "asset_id": package.media_asset_id},
    )
    return job


def _package_dir(package: MediaPackage, *, settings: Settings | None = None) -> Path:
    cfg = settings or get_settings()
    root = Path(cfg.media_root).resolve()
    raw = Path(package.storage_path or "")
    if raw.is_absolute() or ".." in raw.parts or not str(raw).startswith("packages/"):
        raise OriginSyncError("unsafe_package_path", "Package storage_path is unsafe")
    path = (root / raw).resolve()
    try:
        path.relative_to((root / "packages").resolve())
    except ValueError as exc:
        raise OriginSyncError("unsafe_package_path", "Package escapes packages/") from exc
    if not path.is_dir():
        raise OriginSyncError("package_missing", "Local package directory missing")
    return path


def _iter_package_files(package_dir: Path, *, max_objects: int) -> list[Path]:
    files: list[Path] = []
    for path in sorted(package_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.is_symlink():
            raise OriginSyncError("symlink_rejected", "Package contains symlink files")
        files.append(path)
        if len(files) > max_objects:
            raise OriginSyncError("too_many_objects", "Package exceeds origin sync object limit")
    if not files:
        raise OriginSyncError("empty_package", "Package has no files to sync")
    return files


def _content_type_for(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".m3u8":
        return "application/vnd.apple.mpegurl"
    if suffix == ".ts":
        return "video/mp2t"
    if suffix == ".vtt":
        return "text/vtt"
    return None


def sync_package_tree(
    *,
    package: MediaPackage,
    storage: ObjectStorage,
    settings: Settings | None = None,
) -> PackageSyncResult:
    """Upload package files to origin. Idempotent: skip existing keys with matching size."""
    cfg = settings or get_settings()
    package_dir = _package_dir(package, settings=cfg)
    files = _iter_package_files(package_dir, max_objects=int(cfg.origin_sync_max_objects))
    keys = ObjectKeyBuilder(prefix=cfg.media_object_key_prefix or "ifilm")
    prefix = keys.package_root(asset_id=package.media_asset_id, package_id=package.id)

    bytes_synced = 0
    uploaded = 0
    skipped = 0
    for path in files:
        rel = path.relative_to(package_dir).as_posix()
        key = keys.package_object_key(
            asset_id=package.media_asset_id,
            package_id=package.id,
            relative_path=rel,
        )
        local_size = path.stat().st_size
        already = storage.exists(key=key)
        stored = storage.put_file(key=key, source=path, content_type=_content_type_for(path))
        size = stored.size_bytes if stored.size_bytes is not None else local_size
        if size != local_size:
            raise OriginSyncError(
                "size_mismatch",
                f"Origin object size mismatch for {rel}",
            )
        bytes_synced += local_size
        if already:
            skipped += 1
        else:
            uploaded += 1

    return PackageSyncResult(
        package_id=package.id,
        object_count=uploaded + skipped,
        bytes_synced=bytes_synced,
        skipped_existing=skipped,
        object_prefix=prefix,
    )


def execute_origin_sync_job(
    db: Session,
    job: MediaProcessingJob,
    *,
    settings: Settings | None = None,
) -> MediaProcessingJob:
    cfg = settings or get_settings()
    if not origin_package_sync_enabled(cfg):
        job.status = "cancelled"
        job.error_code = "feature_disabled"
        job.error_message = "Origin package sync is disabled"
        job.finished_at = utcnow()
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    package_id = job.target_package_id
    if not package_id:
        raise OriginSyncError("missing_package", "origin_sync job missing target_package_id")
    package = db.get(MediaPackage, package_id)
    if package is None:
        raise OriginSyncError("package_not_found", "Target package not found")

    package.origin_sync_status = ORIGIN_SYNC_STATUS_SYNCING
    package.origin_sync_attempt = int(package.origin_sync_attempt or 0) + 1
    package.origin_sync_error = None
    job.current_step = "syncing"
    job.progress_percent = 10
    db.add(package)
    db.add(job)
    db.commit()

    storage = get_central_origin_storage(cfg)
    try:
        result = sync_package_tree(package=package, storage=storage, settings=cfg)
    except OriginSyncError as exc:
        package.origin_sync_status = ORIGIN_SYNC_STATUS_FAILED
        package.origin_sync_error = str(exc)[:_CLIP_ERROR]
        db.add(package)
        db.commit()
        raise

    package.origin_sync_status = ORIGIN_SYNC_STATUS_SYNCED
    package.origin_synced_at = utcnow()
    package.origin_sync_error = None
    package.origin_object_prefix = result.object_prefix
    package.origin_bytes_synced = result.bytes_synced
    package.origin_object_count = result.object_count
    job.status = "completed"
    job.progress_percent = 100
    job.current_step = "completed"
    job.finished_at = utcnow()
    job.error_code = None
    job.error_message = None
    add_job_event(
        db,
        job,
        "completed",
        "Origin package sync completed",
        {
            "package_id": package.id,
            "object_count": result.object_count,
            "bytes_synced": result.bytes_synced,
            "object_prefix": result.object_prefix,
        },
    )
    db.add(package)
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info(
        "origin_package_sync_completed",
        extra={
            "package_id": package.id,
            "job_id": job.id,
            "object_count": result.object_count,
            "bytes_synced": result.bytes_synced,
        },
    )
    return job
