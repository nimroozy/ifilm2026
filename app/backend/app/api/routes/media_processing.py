"""Admin media processing endpoints (probe jobs)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.config import get_settings
from app.core.deps import DbSession, require_permissions
from app.core.features import require_feature
from app.models.admin import AdminUser
from app.schemas.common import Envelope, paginated
from app.schemas.media_processing import (
    MediaAssetProbeOut,
    ProcessingJobCreateOut,
    ProcessingJobEventOut,
    ProcessingJobOut,
    ProcessingStatusOut,
)
from app.services import media_upload as upload_service
from app.services.media_processing import jobs as processing_jobs
from app.services.media_processing.worker import processing_binaries_ok

router = APIRouter(tags=["media-processing"])


def _job_out(job, *, include_events: bool = False) -> ProcessingJobOut:
    payload = {
        "id": job.id,
        "media_asset_id": job.media_asset_id,
        "job_type": job.job_type,
        "status": job.status,
        "priority": job.priority,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "progress_percent": job.progress_percent,
        "current_step": job.current_step,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "worker_id": job.worker_id,
        "cancel_requested": bool(job.cancel_requested),
        "queued_at": job.queued_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "heartbeat_at": job.heartbeat_at,
        "next_retry_at": job.next_retry_at,
        "created_by_admin_id": job.created_by_admin_id,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "media_asset": MediaAssetProbeOut.model_validate(job.media_asset)
        if job.media_asset is not None
        else None,
        "events": [],
    }
    if include_events:
        payload["events"] = [
            ProcessingJobEventOut.model_validate(event) for event in (job.events or [])
        ]
    return ProcessingJobOut.model_validate(payload)


@router.get("/admin/media/processing/status", response_model=ProcessingStatusOut)
def processing_feature_status(
    _: Annotated[AdminUser, Depends(require_permissions("processing.read"))],
):
    settings = get_settings()
    bins = processing_binaries_ok(settings)
    return ProcessingStatusOut(
        enabled=bool(settings.enable_media_processing),
        ffmpeg_available=bins["ffmpeg"],
        ffprobe_available=bins["ffprobe"],
    )


@router.post(
    "/admin/media/assets/{asset_id}/processing/probe",
    response_model=ProcessingJobCreateOut,
)
def queue_probe(
    asset_id: str,
    db: DbSession,
    response: Response,
    admin: Annotated[AdminUser, Depends(require_permissions("processing.manage"))],
):
    settings = get_settings()
    require_feature("enable_media_processing", settings)
    asset = upload_service.get_asset(db, asset_id)
    job, created = processing_jobs.queue_probe_job(
        db, settings=settings, asset=asset, admin_id=admin.id
    )
    job = processing_jobs.get_job(db, job.id)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return ProcessingJobCreateOut(job=_job_out(job, include_events=True), created=created)


@router.get(
    "/admin/media/assets/{asset_id}/processing",
    response_model=Envelope[ProcessingJobOut],
)
def list_asset_processing(
    asset_id: str,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("processing.read"))],
):
    settings = get_settings()
    require_feature("enable_media_processing", settings)
    upload_service.get_asset(db, asset_id)
    items = processing_jobs.list_jobs_for_asset(db, asset_id)
    return paginated(
        [_job_out(item) for item in items],
        total=len(items),
        page=1,
        page_size=max(len(items), 1),
    )


@router.get("/admin/media/processing/jobs", response_model=Envelope[ProcessingJobOut])
def list_processing_jobs(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("processing.read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    job_type: str | None = Query(None),
    media_asset_id: str | None = Query(None),
):
    settings = get_settings()
    require_feature("enable_media_processing", settings)
    items, total = processing_jobs.list_jobs(
        db,
        status_filter=status_filter,
        job_type=job_type,
        media_asset_id=media_asset_id,
        page=page,
        page_size=page_size,
    )
    return paginated(
        [_job_out(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/admin/media/processing/jobs/{job_id}", response_model=ProcessingJobOut)
def get_processing_job(
    job_id: str,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("processing.read"))],
):
    settings = get_settings()
    require_feature("enable_media_processing", settings)
    job = processing_jobs.get_job(db, job_id)
    return _job_out(job, include_events=True)


@router.post("/admin/media/processing/jobs/{job_id}/retry", response_model=ProcessingJobOut)
def retry_processing_job(
    job_id: str,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("processing.manage"))],
):
    settings = get_settings()
    require_feature("enable_media_processing", settings)
    job = processing_jobs.get_job(db, job_id)
    job = processing_jobs.retry_job(db, settings=settings, job=job)
    job = processing_jobs.get_job(db, job.id)
    return _job_out(job, include_events=True)


@router.delete("/admin/media/processing/jobs/{job_id}", response_model=ProcessingJobOut)
def cancel_processing_job(
    job_id: str,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("processing.manage"))],
):
    settings = get_settings()
    require_feature("enable_media_processing", settings)
    job = processing_jobs.get_job(db, job_id)
    job = processing_jobs.cancel_job(db, job)
    job = processing_jobs.get_job(db, job.id)
    return _job_out(job, include_events=True)
