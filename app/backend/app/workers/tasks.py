"""ARQ worker tasks for upload finalization, encoding, and CDN sync."""

from __future__ import annotations

import logging

from app.db.session import SessionLocal, get_engine
from app.models.media import EncodingJob, UploadJob
from app.services.cdn_sync import enqueue_sync, run_sync_job
from app.services.encoding import complete_encoding, fail_encoding, mark_processing
from app.workers.settings import redis_settings

logger = logging.getLogger(__name__)


async def process_encoding_job(ctx, job_id: int):
    get_engine()
    db = SessionLocal()
    try:
        job = db.get(EncodingJob, job_id)
        if not job:
            logger.error("Encoding job %s not found", job_id)
            return {"ok": False, "error": "not_found"}
        mark_processing(db, job, worker=ctx.get("worker_name", "arq-worker"))
        job = complete_encoding(db, job)
        if job.output_hls_path and job.content_id:
            sync_jobs = enqueue_sync(
                db,
                content_type=job.content_type,
                content_id=job.content_id,
                hls_path=job.output_hls_path,
            )
            for sync_job in sync_jobs:
                run_sync_job(db, sync_job)
        return {"ok": True, "job_id": job.id, "hls_path": job.output_hls_path}
    except Exception as exc:
        logger.exception("Encoding failed for job %s", job_id)
        job = db.get(EncodingJob, job_id)
        if job:
            fail_encoding(db, job, str(exc))
        return {"ok": False, "error": str(exc)}
    finally:
        db.close()


async def process_cdn_sync_job(ctx, sync_job_id: int):
    get_engine()
    db = SessionLocal()
    try:
        from app.models.cdn import CDNSyncJob

        job = db.get(CDNSyncJob, sync_job_id)
        if not job:
            return {"ok": False, "error": "not_found"}
        job = run_sync_job(db, job)
        return {"ok": True, "status": job.status}
    finally:
        db.close()


async def finalize_upload_job(ctx, upload_job_id: int, create_encoding: bool = True):
    get_engine()
    db = SessionLocal()
    try:
        upload = db.get(UploadJob, upload_job_id)
        if not upload:
            return {"ok": False, "error": "not_found"}
        upload.status = "completed"
        upload.progress = 100
        db.add(upload)
        db.commit()
        db.refresh(upload)

        encoding_id = None
        if create_encoding and upload.stored_path:
            encoding = EncodingJob(
                title=upload.filename,
                source_file=upload.stored_path,
                content_type=upload.content_type,
                content_id=upload.content_id,
                upload_job_id=upload.id,
                qualities=["1080p", "720p", "480p", "360p"],
                status="waiting",
                stage="queued",
            )
            db.add(encoding)
            db.commit()
            db.refresh(encoding)
            encoding_id = encoding.id
            await process_encoding_job(ctx, encoding.id)
        return {"ok": True, "upload_id": upload.id, "encoding_id": encoding_id}
    finally:
        db.close()


def _worker_queue_name() -> str:
    from app.core.config import get_settings

    return get_settings().worker_queue_name


class WorkerSettings:
    functions = [process_encoding_job, process_cdn_sync_job, finalize_upload_job]
    redis_settings = redis_settings()
    # arq requires queue_name at import/startup; None makes the worker exit immediately
    queue_name = _worker_queue_name()

    @classmethod
    def on_startup(cls, ctx):
        ctx["worker_name"] = "arq-worker"
