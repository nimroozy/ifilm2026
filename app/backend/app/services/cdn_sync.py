"""Experimental CDN edge synchronization (not production-ready)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.cdn import CDNNode, CDNSyncJob

logger = logging.getLogger(__name__)


def enqueue_sync(
    db: Session,
    *,
    content_type: str,
    content_id: int,
    hls_path: str,
    node_id: int | None = None,
) -> list[CDNSyncJob]:
    settings = get_settings()
    if not settings.enable_cdn_sync:
        return []

    query = db.query(CDNNode).filter(CDNNode.status == "online")
    if node_id is not None:
        query = query.filter(CDNNode.id == node_id)
    nodes = query.all()
    jobs: list[CDNSyncJob] = []
    for node in nodes:
        job = CDNSyncJob(
            node_id=node.id,
            content_type=content_type,
            content_id=content_id,
            hls_path=hls_path,
            status="pending",
        )
        db.add(job)
        jobs.append(job)
    db.commit()
    for job in jobs:
        db.refresh(job)
    return jobs


def run_sync_job(db: Session, job: CDNSyncJob) -> CDNSyncJob:
    settings = get_settings()
    node = db.get(CDNNode, job.node_id)
    job.status = "syncing"
    db.add(job)
    db.commit()

    if not node:
        job.status = "failed"
        job.detail = "CDN node not found"
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    if not node.base_url:
        job.status = "completed"
        job.detail = "Experimental local/no-op sync (node base_url empty)"
        node.last_sync = datetime.now(UTC)
        node.cached_titles = (node.cached_titles or 0) + 1
        db.add(node)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    try:
        url = node.base_url.rstrip("/") + "/sync"
        payload = {
            "content_type": job.content_type,
            "content_id": job.content_id,
            "hls_path": job.hls_path,
        }
        with httpx.Client(timeout=settings.cdn_http_timeout_seconds) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
        job.status = "completed"
        job.detail = f"Synced via HTTP {response.status_code}"
        node.last_sync = datetime.now(UTC)
        node.cached_titles = (node.cached_titles or 0) + 1
        db.add(node)
    except Exception as exc:
        logger.exception("CDN sync failed for node %s", job.node_id)
        job.status = "failed"
        job.detail = str(exc)

    db.add(job)
    db.commit()
    db.refresh(job)
    return job
