from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentAdmin, DbSession
from app.models.cdn import Branch, CDNNode, CDNSyncJob
from app.schemas.cdn import BranchOut, CDNNodeOut, CDNSyncOut, CDNSyncRequest
from app.services.cdn_sync import enqueue_sync, run_sync_job

router = APIRouter(prefix="/admin/cdn", tags=["cdn"])


@router.get("/nodes", response_model=list[CDNNodeOut])
def list_nodes(db: DbSession, _: CurrentAdmin):
    return db.query(CDNNode).order_by(CDNNode.id.asc()).all()


@router.get("/branches", response_model=list[BranchOut])
def list_branches(db: DbSession, _: CurrentAdmin):
    return db.query(Branch).order_by(Branch.id.asc()).all()


@router.post("/sync", response_model=list[CDNSyncOut])
def sync_content(payload: CDNSyncRequest, db: DbSession, _: CurrentAdmin):
    jobs = enqueue_sync(
        db,
        content_type=payload.content_type,
        content_id=payload.content_id,
        hls_path=payload.hls_path,
        node_id=payload.node_id,
    )
    return [run_sync_job(db, job) for job in jobs]


@router.get("/sync/jobs", response_model=list[CDNSyncOut])
def list_sync_jobs(db: DbSession, _: CurrentAdmin):
    return db.query(CDNSyncJob).order_by(CDNSyncJob.id.desc()).limit(100).all()
