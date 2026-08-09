from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.core.deps import DbSession, require_permissions
from app.models.admin import AdminUser
from app.models.media import EncodingJob
from app.schemas.media import EncodingOut
from app.services.cdn_sync import enqueue_sync, run_sync_job
from app.services.encoding import complete_encoding, mark_processing
from app.services.legacy_encoding import require_legacy_encoding_allowed

router = APIRouter(prefix="/admin/encoding", tags=["encoding"])


@router.get("/jobs", response_model=list[EncodingOut])
def list_jobs(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("processing.read"))],
):
    """Legacy EncodingJob list — hard-blocked in production/staging."""
    require_legacy_encoding_allowed()
    return db.query(EncodingJob).order_by(EncodingJob.id.desc()).limit(100).all()


@router.post("/jobs/{job_id}/retry", response_model=EncodingOut)
def retry_job(
    job_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("processing.manage"))],
):
    settings = get_settings()
    require_legacy_encoding_allowed(settings)
    job = db.get(EncodingJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encoding job not found")
    job.status = "waiting"
    job.stage = "queued"
    job.progress = 0
    job.error = None
    db.add(job)
    db.commit()
    # Placeholder packaging only — not production HLS encoding.
    mark_processing(db, job)
    job = complete_encoding(db, job)
    if settings.enable_cdn_sync and job.output_hls_path and job.content_id:
        for sync_job in enqueue_sync(
            db,
            content_type=job.content_type,
            content_id=job.content_id,
            hls_path=job.output_hls_path,
        ):
            run_sync_job(db, sync_job)
    return job
