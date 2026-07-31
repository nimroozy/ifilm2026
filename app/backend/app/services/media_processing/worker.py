"""Background media processing worker loop."""

from __future__ import annotations

import logging
import signal
import time
from types import FrameType

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.services.media_processing.ffmpeg import binary_available, resolve_binary
from app.services.media_processing.jobs import (
    claim_next_job,
    default_worker_id,
    execute_probe_job,
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
    """Validate FFmpeg/ffprobe when processing is enabled. Raises on failure."""
    resolve_binary(settings.ffmpeg_binary, label="ffmpeg")
    resolve_binary(settings.ffprobe_binary, label="ffprobe")


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
    execute_probe_job(db, settings=settings, job=job)
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
        logger.error("FFmpeg/ffprobe validation failed: %s", exc)
        raise SystemExit(2) from exc

    worker_id = default_worker_id(settings)
    logger.info("Media processing worker starting id=%s", worker_id)
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

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
