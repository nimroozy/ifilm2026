"""Encoding orchestration.

IMPORTANT: Current output is placeholder HLS packaging only.
It does not run real ffmpeg multi-bitrate encoding and is not production-ready.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.content import Episode, Movie
from app.models.media import EncodingJob
from app.services.hls import DEFAULT_QUALITIES, write_placeholder_package


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
    qualities = job.qualities or DEFAULT_QUALITIES
    relative = write_placeholder_package(
        content_type=job.content_type,
        content_id=job.content_id or 0,
        qualities=qualities,
        episode_id=None,
    )
    job.output_hls_path = relative
    job.progress = 100
    job.stage = "completed"
    job.status = "completed"
    job.error = None

    if job.content_type == "movie" and job.content_id:
        movie = db.get(Movie, job.content_id)
        if movie:
            movie.hls_path = relative
            movie.qualities = qualities
            db.add(movie)
    elif job.content_type == "episode" and job.content_id:
        episode = db.get(Episode, job.content_id)
        if episode:
            episode.hls_path = relative
            db.add(episode)

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
