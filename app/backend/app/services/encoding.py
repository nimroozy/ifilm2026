"""Legacy EncodingJob helpers.

Real HLS packaging is performed by the media-processing worker (encode_hls).
Placeholder HLS writing via write_placeholder_package has been removed.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.media import EncodingJob


def mark_processing(db: Session, job: EncodingJob, worker: str = "encoder-1") -> EncodingJob:
    job.status = "processing"
    job.stage = "transcoding"
    job.worker = worker
    job.progress = max(job.progress, 5)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def complete_encoding(db: Session, job: EncodingJob) -> EncodingJob:
    """Mark legacy EncodingJob complete without writing placeholder packages.

    Use admin media processing encode-hls for real packages.
    """
    job.progress = 100
    job.stage = "completed"
    job.status = "completed"
    job.error = None
    job.output_hls_path = None
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def fail_encoding(db: Session, job: EncodingJob, error: str) -> EncodingJob:
    job.status = "failed"
    job.stage = "failed"
    job.error = error
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
