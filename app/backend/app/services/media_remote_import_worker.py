"""Dedicated remote media import worker loop (JOB_TYPE_REMOTE_MEDIA_IMPORT only)."""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path
from types import FrameType

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal, get_engine
from app.models.media_processing import REMOTE_MEDIA_IMPORT_WORKER_JOB_TYPES
from app.services.media_processing.jobs import (
    claim_next_job,
    default_worker_id,
    fail_or_retry,
    heartbeat_job,
    recover_stale_jobs,
)
from app.services.media_remote_import import execute_remote_media_import
from app.services.storage import media_root

logger = logging.getLogger(__name__)

_shutdown = False

REQUIRED_WRITABLE_PATHS = ("temp", "originals")


class RemoteImportMountError(RuntimeError):
    """Required remote-import writable paths missing or not writable."""


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("Received signal %s; shutting down after current job", signum)
    _shutdown = True


def _path_writable(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        probe = path / f".remote-import-write-{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def inspect_remote_import_mounts(settings: Settings | None = None) -> dict[str, bool]:
    settings = settings or get_settings()
    root = Path(settings.media_root)
    return {name: _path_writable(root / name) for name in REQUIRED_WRITABLE_PATHS}


def remote_import_mounts_healthy(settings: Settings | None = None) -> bool:
    return all(inspect_remote_import_mounts(settings).values())


def validate_remote_import_mounts(settings: Settings) -> None:
    statuses = inspect_remote_import_mounts(settings)
    missing = [name for name, ok in statuses.items() if not ok]
    if missing:
        raise RemoteImportMountError(
            "Remote import worker requires writable mounts: "
            + ", ".join(f"/data/media/{m}" if str(media_root()).endswith("media") else m for m in missing)
            + f" (under MEDIA_ROOT={settings.media_root})"
        )
    logger.info(
        "remote_import_mounts_ok originals=writable temp=writable media_root=%s",
        settings.media_root,
    )


def database_reachable() -> bool:
    try:
        get_engine()
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            return True
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        logger.exception("remote_import_db_health_failed")
        return False


def feature_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.enable_remote_media_import and settings.enable_uploads)


def worker_startup_health_ok(settings: Settings | None = None) -> bool:
    """Healthy when disabled (idle) or when enabled with writable mounts + DB."""
    settings = settings or get_settings()
    if not feature_enabled(settings):
        return True
    if not remote_import_mounts_healthy(settings):
        return False
    return database_reachable()


def run_once(db: Session, *, settings: Settings, worker_id: str) -> bool:
    if not feature_enabled(settings):
        return False
    recover_stale_jobs(
        db, settings=settings, allowed_job_types=REMOTE_MEDIA_IMPORT_WORKER_JOB_TYPES
    )
    job = claim_next_job(
        db,
        settings=settings,
        worker_id=worker_id,
        allowed_job_types=REMOTE_MEDIA_IMPORT_WORKER_JOB_TYPES,
    )
    if job is None:
        return False
    heartbeat_job(db, job)
    if not feature_enabled(settings):
        fail_or_retry(
            db,
            settings=settings,
            job=job,
            error_code="feature_disabled",
            message="Remote media import is disabled",
            transient=False,
        )
        db.commit()
        return True
    execute_remote_media_import(db, settings=settings, job=job)
    return True


def run_forever(*, settings: Settings | None = None) -> None:
    global _shutdown
    _shutdown = False
    settings = settings or get_settings()
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    if not feature_enabled(settings):
        logger.warning(
            "Remote media import worker idle: ENABLE_REMOTE_MEDIA_IMPORT/ENABLE_UPLOADS disabled"
        )
        while not _shutdown:
            time.sleep(max(2.0, float(settings.media_processing_poll_seconds)))
        return

    try:
        validate_remote_import_mounts(settings)
    except RemoteImportMountError as exc:
        logger.error("%s", exc)
        raise SystemExit(3) from exc

    if not database_reachable():
        logger.error("Database unreachable; remote import worker exiting")
        raise SystemExit(4)

    worker_id = default_worker_id(settings)
    # Distinct default id prefix when MEDIA_PROCESSING_WORKER_ID unset.
    if not (settings.media_processing_worker_id or "").strip():
        worker_id = f"remote-import-{worker_id}"
    logger.info(
        "Remote media import worker starting id=%s job_types=%s",
        worker_id,
        sorted(REMOTE_MEDIA_IMPORT_WORKER_JOB_TYPES),
    )

    get_engine()

    while not _shutdown:
        db = SessionLocal()
        try:
            processed = run_once(db, settings=settings, worker_id=worker_id)
        except Exception:  # noqa: BLE001
            logger.exception("Remote import worker loop error")
            processed = False
        finally:
            db.close()
        if not processed:
            time.sleep(max(0.5, float(settings.media_processing_poll_seconds)))
