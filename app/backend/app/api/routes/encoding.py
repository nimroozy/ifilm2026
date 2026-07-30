from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentAdmin, DbSession
from app.models.media import EncodingJob
from app.schemas.media import EncodingOut
from app.services.cdn_sync import enqueue_sync, run_sync_job
from app.services.encoding import complete_encoding, mark_processing

router = APIRouter(prefix="/admin/encoding", tags=["encoding"])


@router.get("/jobs", response_model=list[EncodingOut])
def list_jobs(db: DbSession, _: CurrentAdmin):
    return db.query(EncodingJob).order_by(EncodingJob.id.desc()).limit(100).all()


@router.post("/jobs/{job_id}/retry", response_model=EncodingOut)
def retry_job(job_id: int, db: DbSession, _: CurrentAdmin):
    job = db.get(EncodingJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encoding job not found")
    job.status = "waiting"
    job.stage = "queued"
    job.progress = 0
    job.error = None
    db.add(job)
    db.commit()
    mark_processing(db, job)
    job = complete_encoding(db, job)
    if job.output_hls_path and job.content_id:
        for sync_job in enqueue_sync(
            db,
            content_type=job.content_type,
            content_id=job.content_id,
            hls_path=job.output_hls_path,
        ):
            run_sync_job(db, sync_job)
    return job
