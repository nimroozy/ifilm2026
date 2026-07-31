"""Background media processing worker loop."""

from __future__ import annotations

import logging
import signal
import time
from types import FrameType

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal, get_engine
from app.models.media_processing import JOB_TYPE_ENCODE_HLS, JOB_TYPE_PROBE
from app.services.media_processing.ffmpeg import binary_available, resolve_binary
from app.services.media_processing.jobs import (
    claim_next_job,
    default_worker_id,
    execute_probe_job,
    fail_or_retry,
    heartbeat_job,
    recover_stale_jobs,
)

logger = logging.getLogger(__name__)

_shutdown = False


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("Received signal %s; shutting down after current job", signum)
    _shutdown = True


def validate_binaries(settings: Settings) -> None:
    """Validate required binaries for the enabled feature set.

    Probe always needs ffprobe when media processing is enabled.
    FFmpeg is required only when HLS encoding is also enabled.
    """
    resolve_binary(settings.ffprobe_binary, label="ffprobe")
    if settings.enable_hls_encoding:
        resolve_binary(settings.ffmpeg_binary, label="ffmpeg")


def processing_binaries_ok(settings: Settings) -> dict[str, bool]:
    return {
        "ffmpeg": binary_available(settings.ffmpeg_binary),
        "ffprobe": binary_available(settings.ffprobe_binary),
    }


def run_once(db: Session, *, settings: Settings, worker_id: str) -> bool:
    """Claim and run at most one job. Returns True if a job was processed."""
    recover_stale_jobs(db, settings=settings)
    job = claim_next_job(db, settings=settings, worker_id=worker_id)
    if job is None:
        return False
    heartbeat_job(db, job)
    if job.job_type == JOB_TYPE_PROBE:
        execute_probe_job(db, settings=settings, job=job)
    elif job.job_type == JOB_TYPE_ENCODE_HLS:
        if not settings.enable_hls_encoding:
            from app.models.media_encoding import MediaPackage
            from app.services.media_processing.package_paths import (
                remove_tree_if_exists,
                work_package_dir,
            )
            from app.services.storage import media_root

            package = (
                db.query(MediaPackage).filter(MediaPackage.processing_job_id == job.id).first()
            )
            if package is not None:
                package.status = "failed"
                package.error_code = "hls_encoding_disabled"
                package.error_message = "HLS encoding is disabled"
                if package.work_path:
                    remove_tree_if_exists(media_root() / package.work_path)
                remove_tree_if_exists(work_package_dir(job.id, create=False))
                package.work_path = None
                db.add(package)
            fail_or_retry(
                db,
                settings=settings,
                job=job,
                error_code="hls_encoding_disabled",
                message="HLS encoding is disabled",
                transient=False,
            )
            db.commit()
            return True
        from app.services.media_processing.encode_job import execute_encode_hls_job

        execute_encode_hls_job(db, settings=settings, job=job)
    else:
        logger.error("Unsupported job type %s for job %s", job.job_type, job.id)
        fail_or_retry(
            db,
            settings=settings,
            job=job,
            error_code="unsupported_job_type",
            message=f"Unsupported job type: {job.job_type}",
            transient=False,
        )
        db.commit()
    return True


def run_forever(*, settings: Settings | None = None) -> None:
    global _shutdown
    _shutdown = False
    settings = settings or get_settings()
    if not settings.enable_media_processing:
        logger.error("ENABLE_MEDIA_PROCESSING is false; worker exiting")
        raise SystemExit(1)

    try:
        validate_binaries(settings)
    except Exception as exc:  # noqa: BLE001
        logger.error("Binary validation failed: %s", exc)
        raise SystemExit(2) from exc

    worker_id = default_worker_id(settings)
    logger.info(
        "Media processing worker starting id=%s hls_encoding=%s",
        worker_id,
        bool(settings.enable_hls_encoding),
    )
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    get_engine()

    while not _shutdown:
        db = SessionLocal()
        try:
            processed = run_once(db, settings=settings, worker_id=worker_id)
        except Exception:  # noqa: BLE001
            logger.exception("Worker loop error")
            processed = False
        finally:
            db.close()
        if not processed:
            time.sleep(max(0.5, float(settings.media_processing_poll_seconds)))
