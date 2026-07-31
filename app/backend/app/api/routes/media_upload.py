"""Admin media upload foundation endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile, status

from app.core.config import get_settings
from app.core.deps import DbSession, require_permissions
from app.core.features import require_feature
from app.models.admin import AdminUser
from app.models.media_assets import MediaAsset
from app.schemas.common import Envelope, paginated
from app.schemas.media_upload import (
    MediaAssetOut,
    UploadSessionCreate,
    UploadSessionCreateOut,
    UploadSessionOut,
)
from app.services import media_upload as upload_service

router = APIRouter(tags=["media-upload"])


@router.post(
    "/admin/media/sessions",
    response_model=UploadSessionCreateOut,
    status_code=status.HTTP_201_CREATED,
)
def create_media_upload_session(
    payload: UploadSessionCreate,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("upload.manage"))],
):
    settings = get_settings()
    require_feature("enable_uploads", settings)
    session, asset = upload_service.create_upload_session(
        db,
        settings=settings,
        admin_id=admin.id,
        filename=payload.filename,
        mime_type=payload.mime_type,
        size_bytes=payload.size_bytes,
        category=payload.category,
        movie_id=payload.movie_id,
        series_id=payload.series_id,
        season_id=payload.season_id,
        episode_id=payload.episode_id,
    )
    return UploadSessionCreateOut(
        session=UploadSessionOut.model_validate(
            {
                **{
                    k: v
                    for k, v in upload_service.session_out_dict(session).items()
                    if k != "media_asset"
                },
                "media_asset": MediaAssetOut.model_validate(asset),
            }
        ),
        media_asset=MediaAssetOut.model_validate(asset),
    )


@router.put("/admin/media/sessions/{session_id}", response_model=UploadSessionOut)
async def put_media_upload_file(
    session_id: str,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("upload.manage"))],
    file: UploadFile = File(...),
    upload_offset: Annotated[int, Header(alias="Upload-Offset")] = 0,
    upload_complete: Annotated[str | None, Header(alias="Upload-Complete")] = None,
):
    """Append a chunk to an upload session.

    Headers:
    - ``Upload-Offset``: byte offset where this chunk begins (must equal
      ``bytes_received``). ``0`` truncates/creates the temp file for a fresh
      pending/uploading session.
    - ``Upload-Complete``: ``true``/``1`` means this is the final request; if
      ``bytes_received != expected_size_bytes`` after the body, the session
      fails with HTTP 400. Omit or ``false`` to leave an incomplete session
      resumable.

    Terminal sessions (completed/failed/cancelled) and expired sessions reject
    further chunks. Wrong offsets return HTTP 409.
    """
    settings = get_settings()
    require_feature("enable_uploads", settings)
    session = upload_service.get_session(db, session_id)
    complete_flag = (upload_complete or "").strip().lower() in {"1", "true", "yes"}
    session = await upload_service.stream_upload_to_session(
        db,
        settings=settings,
        session=session,
        file=file,
        upload_offset=upload_offset,
        upload_complete=complete_flag,
    )
    return UploadSessionOut.model_validate(upload_service.session_out_dict(session))


@router.get("/admin/media/sessions/{session_id}", response_model=UploadSessionOut)
def get_media_upload_progress(
    session_id: str,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("upload.read"))],
):
    settings = get_settings()
    require_feature("enable_uploads", settings)
    session = upload_service.get_session(db, session_id)
    return UploadSessionOut.model_validate(upload_service.session_out_dict(session))


@router.delete("/admin/media/sessions/{session_id}", response_model=UploadSessionOut)
def cancel_media_upload_session(
    session_id: str,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("upload.manage"))],
):
    settings = get_settings()
    require_feature("enable_uploads", settings)
    session = upload_service.get_session(db, session_id)
    session = upload_service.cancel_upload_session(db, session)
    return UploadSessionOut.model_validate(upload_service.session_out_dict(session))


@router.get("/admin/media/assets/{asset_id}", response_model=MediaAssetOut)
def get_media_asset(
    asset_id: str,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("upload.read"))],
):
    settings = get_settings()
    require_feature("enable_uploads", settings)
    asset = upload_service.get_asset(db, asset_id)
    return MediaAssetOut.model_validate(asset)


@router.get("/admin/media/assets", response_model=Envelope[MediaAssetOut])
def list_media_assets(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("upload.read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
):
    settings = get_settings()
    require_feature("enable_uploads", settings)
    query = db.query(MediaAsset)
    if status_filter:
        query = query.filter(MediaAsset.upload_status == status_filter)
    total = query.count()
    items = (
        query.order_by(MediaAsset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated(
        [MediaAssetOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
