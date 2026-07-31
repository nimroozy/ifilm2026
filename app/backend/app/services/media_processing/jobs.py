"""Media processing job orchestration (queue, claim, probe, retry, cancel)."""

from __future__ import annotations

import socket
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.models.media_processing import (
    ACTIVE_JOB_STATUSES,
    JOB_TYPE_ENCODE_HLS,
    JOB_TYPE_PROBE,
    TERMINAL_JOB_STATUSES,
    MediaProcessingJob,
    MediaProcessingJobEvent,
)
from app.services.media_processing.errors import (
    DIAGNOSTIC_MAX_CHARS,
    PROGRESS_CLAIMED,
    PROGRESS_COMPLETED,
    PROGRESS_PARSING,
    PROGRESS_QUEUED,
    PROGRESS_RUNNING_FFPROBE,
    PROGRESS_SAVING,
    PROGRESS_VALIDATING,
    MediaProcessingError,
    PermanentProcessingError,
    ProbeCancelledError,
    TransientProcessingError,
)
from app.services.media_processing.ffprobe import run_ffprobe
from app.services.media_processing.parser import parse_ffprobe_payload
from app.services.media_processing.paths import resolve_completed_asset_path


def default_worker_id(settings: Settings) -> str:
    configured = (settings.media_processing_worker_id or "").strip()
    if configured:
        return configured
    return f"{socket.gethostname()}:{new_uuid()[:8]}"


def clip_diagnostic(message: str | None, limit: int = DIAGNOSTIC_MAX_CHARS) -> str | None:
    if message is None:
        return None
    text_value = str(message).strip()
    if len(text_value) <= limit:
        return text_value
    return text_value[: limit - 3] + "..."


def _clip(message: str | None, limit: int = DIAGNOSTIC_MAX_CHARS) -> str | None:
    return clip_diagnostic(message, limit)


def add_job_event(
    db: Session,
    job: MediaProcessingJob,
    event_type: str,
    message: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        MediaProcessingJobEvent(
            id=new_uuid(),
            job_id=job.id,
            event_type=event_type,
            message=_clip(message, 1024),
            details=details,
        )
    )


def get_job(db: Session, job_id: str) -> MediaProcessingJob:
    job = (
        db.query(MediaProcessingJob)
        .options(joinedload(MediaProcessingJob.media_asset), joinedload(MediaProcessingJob.events))
        .filter(MediaProcessingJob.id == job_id)
        .first()
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Processing job not found"
        )
    return job


def list_jobs_for_asset(db: Session, asset_id: str) -> list[MediaProcessingJob]:
    return (
        db.query(MediaProcessingJob)
        .filter(MediaProcessingJob.media_asset_id == asset_id)
        .order_by(MediaProcessingJob.created_at.desc())
        .all()
    )


def list_jobs(
    db: Session,
    *,
    status_filter: str | None,
    job_type: str | None,
    media_asset_id: str | None,
    page: int,
    page_size: int,
) -> tuple[list[MediaProcessingJob], int]:
    query = db.query(MediaProcessingJob)
    if status_filter:
        query = query.filter(MediaProcessingJob.status == status_filter)
    if job_type:
        query = query.filter(MediaProcessingJob.job_type == job_type)
    if media_asset_id:
        query = query.filter(MediaProcessingJob.media_asset_id == media_asset_id)
    total = query.count()
    items = (
        query.options(joinedload(MediaProcessingJob.media_asset))
        .order_by(MediaProcessingJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def find_active_probe_job(db: Session, asset_id: str) -> MediaProcessingJob | None:
    return (
        db.query(MediaProcessingJob)
        .filter(
            MediaProcessingJob.media_asset_id == asset_id,
            MediaProcessingJob.job_type == JOB_TYPE_PROBE,
            MediaProcessingJob.status.in_(tuple(ACTIVE_JOB_STATUSES)),
        )
        .first()
    )


def queue_probe_job(
    db: Session,
    *,
    settings: Settings,
    asset: MediaAsset,
    admin_id: int | None,
) -> tuple[MediaProcessingJob, bool]:
    """Create a queued probe job. Returns (job, created)."""
    if asset.upload_status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Probe requires a completed upload",
        )
    if (asset.storage_backend or "").lower() != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported storage backend for processing",
        )

    existing = find_active_probe_job(db, asset.id)
    if existing is not None:
        return existing, False

    job = MediaProcessingJob(
        id=new_uuid(),
        media_asset_id=asset.id,
        job_type=JOB_TYPE_PROBE,
        status="queued",
        priority=100,
        attempt_count=0,
        max_attempts=settings.media_processing_max_attempts,
        progress_percent=PROGRESS_QUEUED,
        current_step="queued",
        queued_at=utcnow(),
        created_by_admin_id=admin_id,
    )
    try:
        db.add(job)
        db.flush()
        add_job_event(db, job, "queued", "Probe job queued")
        asset.processing_status = "queued"
        db.add(asset)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = find_active_probe_job(db, asset.id)
        if existing is not None:
            return existing, False
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Active probe job already exists",
        ) from None
    db.refresh(job)
    return job, True


def retry_job(db: Session, *, settings: Settings, job: MediaProcessingJob) -> MediaProcessingJob:
    if job.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed jobs can be retried",
        )
    if job.attempt_count >= job.max_attempts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Maximum attempts exhausted",
        )
    if job.job_type == JOB_TYPE_PROBE:
        active = find_active_probe_job(db, job.media_asset_id)
        conflict_detail = "An active probe job already exists for this asset"
    elif job.job_type == JOB_TYPE_ENCODE_HLS:
        from app.services.media_processing.encode_job import find_active_encode_job

        active = find_active_encode_job(db, job.media_asset_id)
        conflict_detail = "An active HLS encode job already exists for this asset"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported job type: {job.job_type}",
        )
    if active is not None and active.id != job.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=conflict_detail,
        )

    job.status = "queued"
    job.progress_percent = PROGRESS_QUEUED
    job.current_step = "queued"
    job.error_code = None
    job.error_message = None
    job.worker_id = None
    job.cancel_requested = False
    job.started_at = None
    job.finished_at = None
    job.heartbeat_at = None
    job.next_retry_at = None
    job.queued_at = utcnow()
    if job.media_asset:
        job.media_asset.processing_status = "queued"
        db.add(job.media_asset)
    if job.job_type == JOB_TYPE_ENCODE_HLS:
        from app.models.media_encoding import MediaPackage

        package = db.query(MediaPackage).filter(MediaPackage.processing_job_id == job.id).first()
        if package is not None:
            package.status = "pending"
            package.error_code = None
            package.error_message = None
            package.completed_at = None
            package.storage_path = None
            package.master_playlist_path = None
            package.work_path = None
            package.rendition_count = 0
            db.add(package)
    add_job_event(db, job, "queued", "Job re-queued after failure")
    db.add(job)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=conflict_detail,
        ) from exc
    db.refresh(job)
    return job


def cancel_job(db: Session, job: MediaProcessingJob) -> MediaProcessingJob:
    if job.status in TERMINAL_JOB_STATUSES:
        return job

    if job.status in {"queued", "retry_wait"}:
        job.status = "cancelled"
        job.finished_at = utcnow()
        job.current_step = "cancelled"
        job.cancel_requested = True
        add_job_event(db, job, "cancelled", "Job cancelled before execution")
        if job.media_asset and job.media_asset.processing_status in {
            "queued",
            "processing",
            "retry_wait",
        }:
            job.media_asset.processing_status = "cancelled"
            db.add(job.media_asset)
        if job.job_type == JOB_TYPE_ENCODE_HLS:
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
                package.status = "cancelled"
                package.error_code = "cancelled"
                package.error_message = "Job cancelled before execution"
                if package.work_path:
                    remove_tree_if_exists(media_root() / package.work_path)
                remove_tree_if_exists(work_package_dir(job.id, create=False))
                package.work_path = None
                db.add(package)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    # running — signal cancellation; worker finalizes
    job.cancel_requested = True
    add_job_event(db, job, "cancelled", "Cancellation requested for running job")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _eligible_claim_filter(now):
    return or_(
        MediaProcessingJob.status == "queued",
        and_(
            MediaProcessingJob.status == "retry_wait",
            or_(
                MediaProcessingJob.next_retry_at.is_(None), MediaProcessingJob.next_retry_at <= now
            ),
        ),
    )


def claim_next_job(db: Session, *, settings: Settings, worker_id: str) -> MediaProcessingJob | None:
    """Atomically claim one eligible job. Uses SKIP LOCKED on PostgreSQL."""
    now = utcnow()
    dialect = db.bind.dialect.name if db.bind is not None else ""

    if dialect == "postgresql":
        row = db.execute(
            text(
                """
                SELECT id FROM media_processing_jobs
                WHERE (
                    status = 'queued'
                    OR (status = 'retry_wait' AND (next_retry_at IS NULL OR next_retry_at <= :now))
                )
                AND cancel_requested = false
                ORDER BY priority ASC, queued_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            ),
            {"now": now},
        ).first()
        if row is None:
            return None
        job = db.get(MediaProcessingJob, row[0])
    else:
        job = (
            db.query(MediaProcessingJob)
            .filter(_eligible_claim_filter(now), MediaProcessingJob.cancel_requested.is_(False))
            .order_by(MediaProcessingJob.priority.asc(), MediaProcessingJob.queued_at.asc())
            .with_for_update()
            .first()
        )

    if job is None:
        return None

    job.status = "running"
    job.worker_id = worker_id
    job.attempt_count = int(job.attempt_count or 0) + 1
    job.started_at = now
    job.heartbeat_at = now
    job.finished_at = None
    job.next_retry_at = None
    job.progress_percent = PROGRESS_CLAIMED
    job.current_step = "claimed"
    job.error_code = None
    job.error_message = None
    if job.media_asset:
        job.media_asset.processing_status = "processing"
        db.add(job.media_asset)
    add_job_event(db, job, "claimed", f"Claimed by {worker_id}")
    add_job_event(db, job, "started", f"{job.job_type} execution started")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def heartbeat_job(db: Session, job: MediaProcessingJob) -> None:
    job.heartbeat_at = utcnow()
    db.add(job)
    db.commit()


def recover_stale_jobs(db: Session, *, settings: Settings) -> int:
    """Move stale running jobs to retry_wait or failed. Returns count recovered."""
    threshold = utcnow() - timedelta(seconds=settings.media_processing_stale_after_seconds)
    stale = (
        db.query(MediaProcessingJob)
        .filter(
            MediaProcessingJob.status == "running",
            MediaProcessingJob.heartbeat_at.is_not(None),
            MediaProcessingJob.heartbeat_at < threshold,
        )
        .with_for_update()
        .all()
    )
    count = 0
    for job in stale:
        count += 1
        add_job_event(db, job, "stale_recovered", "Stale running job recovered")
        _fail_or_retry(
            db,
            settings=settings,
            job=job,
            error_code="stale_worker",
            message="Worker heartbeat expired",
            transient=True,
        )
    if count:
        db.commit()
    return count


def fail_or_retry(
    db: Session,
    *,
    settings: Settings,
    job: MediaProcessingJob,
    error_code: str,
    message: str,
    transient: bool,
) -> None:
    _fail_or_retry(
        db,
        settings=settings,
        job=job,
        error_code=error_code,
        message=message,
        transient=transient,
    )


def _fail_or_retry(
    db: Session,
    *,
    settings: Settings,
    job: MediaProcessingJob,
    error_code: str,
    message: str,
    transient: bool,
) -> None:
    job.error_code = error_code
    job.error_message = _clip(message)
    job.worker_id = None
    job.heartbeat_at = None
    job.started_at = job.started_at or utcnow()

    if job.cancel_requested:
        job.status = "cancelled"
        job.finished_at = utcnow()
        job.current_step = "cancelled"
        job.progress_percent = job.progress_percent or PROGRESS_CLAIMED
        add_job_event(db, job, "cancelled", "Cancelled during failure handling")
        if job.media_asset:
            job.media_asset.processing_status = "cancelled"
            db.add(job.media_asset)
        db.add(job)
        return

    if transient and job.attempt_count < job.max_attempts:
        delay = settings.media_processing_retry_base_seconds * (2 ** max(0, job.attempt_count - 1))
        job.status = "retry_wait"
        job.next_retry_at = utcnow() + timedelta(seconds=delay)
        job.current_step = "retry_wait"
        job.finished_at = None
        add_job_event(
            db,
            job,
            "retry_scheduled",
            f"Retry scheduled in {delay}s",
            {"attempt": job.attempt_count, "max_attempts": job.max_attempts},
        )
        if job.media_asset:
            job.media_asset.processing_status = "retry_wait"
            db.add(job.media_asset)
    else:
        job.status = "failed"
        job.finished_at = utcnow()
        job.current_step = "failed"
        add_job_event(db, job, "failed", job.error_message)
        if job.media_asset:
            job.media_asset.processing_status = "failed"
            db.add(job.media_asset)
    db.add(job)


def execute_probe_job(
    db: Session, *, settings: Settings, job: MediaProcessingJob
) -> MediaProcessingJob:
    asset = job.media_asset or db.get(MediaAsset, job.media_asset_id)
    if asset is None:
        _fail_or_retry(
            db,
            settings=settings,
            job=job,
            error_code="asset_missing",
            message="Media asset missing",
            transient=False,
        )
        db.commit()
        db.refresh(job)
        return job

    def cancel_check() -> bool:
        db.refresh(job)
        return bool(job.cancel_requested)

    try:
        job.progress_percent = PROGRESS_VALIDATING
        job.current_step = "validating_source"
        db.add(job)
        db.commit()

        path = resolve_completed_asset_path(asset)
        # Capture checksum of file bytes length for immutability assertion in tests.
        size_before = path.stat().st_size

        if cancel_check():
            raise ProbeCancelledError("Probe cancelled")

        job.progress_percent = PROGRESS_RUNNING_FFPROBE
        job.current_step = "running_ffprobe"
        job.heartbeat_at = utcnow()
        db.add(job)
        db.commit()

        raw, _result = run_ffprobe(settings, path, cancel_check=cancel_check)

        job.progress_percent = PROGRESS_PARSING
        job.current_step = "parsing_metadata"
        job.heartbeat_at = utcnow()
        db.add(job)
        db.commit()

        meta = parse_ffprobe_payload(raw, probe_version="ffprobe-json-v1")

        job.progress_percent = PROGRESS_SAVING
        job.current_step = "saving_metadata"
        db.add(job)
        db.commit()

        if path.stat().st_size != size_before:
            raise PermanentProcessingError(
                "Source media file changed during probe", code="source_changed"
            )

        asset.container_format = meta.container_format
        asset.duration_seconds = meta.duration_seconds
        asset.overall_bitrate = meta.overall_bitrate
        asset.video_codec = meta.video_codec
        asset.video_profile = meta.video_profile
        asset.width = meta.video_width
        asset.height = meta.video_height
        asset.display_aspect_ratio = meta.display_aspect_ratio
        asset.video_frame_rate = meta.video_frame_rate
        asset.video_bitrate = meta.video_bitrate
        asset.pixel_format = meta.pixel_format
        asset.audio_codec = meta.audio_codec
        asset.audio_channels = meta.audio_channels
        asset.audio_channel_layout = meta.audio_channel_layout
        asset.audio_sample_rate = meta.audio_sample_rate
        asset.audio_bitrate = meta.audio_bitrate
        asset.audio_stream_count = meta.audio_stream_count
        asset.subtitle_stream_count = meta.subtitle_stream_count
        asset.probe_json = meta.filtered_probe
        asset.probe_version = meta.probe_version
        asset.probed_at = utcnow()
        asset.processing_status = "completed"

        job.status = "completed"
        job.progress_percent = PROGRESS_COMPLETED
        job.current_step = "completed"
        job.finished_at = utcnow()
        job.heartbeat_at = utcnow()
        job.error_code = None
        job.error_message = None
        add_job_event(db, job, "completed", "Probe completed")
        db.add(asset)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    except ProbeCancelledError as exc:
        job.cancel_requested = True
        _fail_or_retry(
            db,
            settings=settings,
            job=job,
            error_code=exc.code,
            message=str(exc),
            transient=False,
        )
        db.commit()
        db.refresh(job)
        return job
    except MediaProcessingError as exc:
        _fail_or_retry(
            db,
            settings=settings,
            job=job,
            error_code=exc.code,
            message=str(exc),
            transient=bool(exc.transient),
        )
        db.commit()
        db.refresh(job)
        return job
    except Exception as exc:  # noqa: BLE001
        _fail_or_retry(
            db,
            settings=settings,
            job=job,
            error_code="internal_error",
            message="Unexpected processing failure",
            transient=isinstance(exc, TransientProcessingError),
        )
        db.commit()
        db.refresh(job)
        return job
