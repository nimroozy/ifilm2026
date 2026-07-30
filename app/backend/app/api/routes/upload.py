from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.core.deps import CurrentAdmin, DbSession
from app.models.media import EncodingJob, UploadJob
from app.schemas.common import Message
from app.schemas.media import EncodingOut, UploadCreate, UploadOut
from app.services.encoding import complete_encoding, mark_processing
from app.services.storage import upload_dir

router = APIRouter(tags=["upload"])


@router.post("/admin/uploads", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
def create_upload(payload: UploadCreate, db: DbSession, admin: CurrentAdmin):
    settings = get_settings()
    if payload.size_bytes > settings.upload_max_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large")
    job = UploadJob(
        filename=payload.filename,
        content_type=payload.content_type,
        content_id=payload.content_id,
        size_bytes=payload.size_bytes,
        status="pending",
        progress=0,
        created_by_admin_id=admin.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.post("/admin/uploads/{upload_id}/file", response_model=UploadOut)
async def upload_file(upload_id: int, db: DbSession, _: CurrentAdmin, file: UploadFile = File(...)):
    job = db.get(UploadJob, upload_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload job not found")

    dest_dir = upload_dir() / str(job.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (file.filename or job.filename)
    job.status = "uploading"
    db.add(job)
    db.commit()

    size = 0
    async with aiofiles.open(dest, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            await out.write(chunk)

    job.stored_path = str(dest)
    job.size_bytes = size
    job.progress = 100
    job.status = "completed"
    db.add(job)

    encoding = EncodingJob(
        title=job.filename,
        source_file=str(dest),
        content_type=job.content_type,
        content_id=job.content_id,
        upload_job_id=job.id,
        qualities=["1080p", "720p", "480p", "360p"],
        status="waiting",
        stage="queued",
    )
    db.add(encoding)
    db.commit()
    db.refresh(job)
    db.refresh(encoding)

    # Inline foundation processing so local/dev works without Redis.
    mark_processing(db, encoding)
    complete_encoding(db, encoding)
    db.refresh(job)
    return job


@router.get("/admin/uploads", response_model=list[UploadOut])
def list_uploads(db: DbSession, _: CurrentAdmin):
    return db.query(UploadJob).order_by(UploadJob.id.desc()).limit(100).all()
