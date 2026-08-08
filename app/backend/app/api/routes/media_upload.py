"""Admin media upload foundation endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status

from app.core.config import get_settings
from app.core.deps import PERMISSION_ALIASES, DbSession, admin_permissions, require_permissions
from app.core.features import require_feature
from app.models.admin import AdminUser
from app.models.media_assets import MediaAsset
from app.schemas.common import Envelope, paginated
from app.schemas.media_upload import (
    ExternalMediaAttachRequest,
    MediaAssetDeleteOut,
    MediaAssetDeleteRequest,
    MediaAssetDetachRequest,
    MediaAssetLinkRequest,
    MediaAssetOut,
    MediaAssetUsagesOut,
    StaleTempCleanupOut,
    UploadSessionCreate,
    UploadSessionCreateOut,
    UploadSessionOut,
)
from app.services import media_delete, media_linking, media_storage_health
from app.services import media_upload as upload_service
from app.services.media_external_attach import attach_external_media, media_asset_to_out

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
                "media_asset": MediaAssetOut.model_validate(media_asset_to_out(asset)),
            }
        ),
        media_asset=MediaAssetOut.model_validate(media_asset_to_out(asset)),
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
    return MediaAssetOut.model_validate(media_asset_to_out(asset))


@router.get("/admin/media/assets", response_model=Envelope[MediaAssetOut])
def list_media_assets(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("upload.read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    movie_id: int | None = Query(None, ge=1),
    episode_id: int | None = Query(None, ge=1),
    unassigned: bool | None = Query(None),
    category: str | None = Query(None),
    q: str | None = Query(None, max_length=256),
    video_only: bool = Query(False),
    linkable_only: bool = Query(False),
):
    settings = get_settings()
    require_feature("enable_uploads", settings)
    if movie_id is not None and episode_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide only one of movie_id or episode_id",
        )
    query = media_linking.list_assets_query(
        db,
        status_filter=status_filter,
        movie_id=movie_id,
        episode_id=episode_id,
        unassigned=unassigned,
        category=category,
        q=q,
        video_only=video_only,
        linkable_only=linkable_only,
    )
    total = query.count()
    items = (
        query.order_by(MediaAsset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated(
        [MediaAssetOut.model_validate(media_asset_to_out(item)) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/admin/media/external",
    response_model=MediaAssetOut,
    status_code=status.HTTP_201_CREATED,
)
def attach_external_media_asset(
    payload: ExternalMediaAttachRequest,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("upload.manage"))],
):
    """Validate an HTTPS MP4/HLS URL and attach it as external media."""
    settings = get_settings()
    require_feature("enable_uploads", settings)
    movie_id = payload.owner_id if payload.owner_type == "movie" else None
    episode_id = payload.owner_id if payload.owner_type == "episode" else None
    asset = attach_external_media(
        db,
        url=payload.url,
        movie_id=movie_id,
        episode_id=episode_id,
        admin_id=admin.id,
        category=payload.category,
        acknowledge_unprotected_external=payload.acknowledge_unprotected_external,
    )
    return MediaAssetOut.model_validate(media_asset_to_out(asset))


@router.post(
    "/admin/media/assets/{asset_id}/link",
    response_model=MediaAssetOut,
)
def link_media_asset(
    asset_id: str,
    payload: MediaAssetLinkRequest,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("upload.manage"))],
):
    settings = get_settings()
    require_feature("enable_uploads", settings)
    asset = media_linking.attach_asset(
        db,
        asset_id=asset_id,
        owner_type=payload.owner_type,  # type: ignore[arg-type]
        owner_id=payload.owner_id,
        admin_id=admin.id,
    )
    return MediaAssetOut.model_validate(media_asset_to_out(asset))


@router.post(
    "/admin/media/assets/{asset_id}/detach",
    response_model=MediaAssetOut,
)
def detach_media_asset(
    asset_id: str,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("upload.manage"))],
    payload: MediaAssetDetachRequest | None = None,
):
    settings = get_settings()
    require_feature("enable_uploads", settings)
    body = payload or MediaAssetDetachRequest()
    allow_force = False
    if body.force_unpublish:
        publish_aliases = PERMISSION_ALIASES.get("catalog.publish", frozenset({"catalog.publish"}))
        allow_force = not admin_permissions(admin).isdisjoint(publish_aliases)
        if not allow_force:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="catalog.publish permission required to force unpublish on detach",
            )
    asset = media_linking.detach_asset(
        db,
        asset_id=asset_id,
        admin_id=admin.id,
        force_unpublish=body.force_unpublish,
        allow_force_unpublish=allow_force,
    )
    return MediaAssetOut.model_validate(media_asset_to_out(asset))


@router.get("/admin/media/assets/{asset_id}/usages", response_model=MediaAssetUsagesOut)
def get_media_asset_usages(
    asset_id: str,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("upload.read"))],
):
    settings = get_settings()
    require_feature("enable_uploads", settings)
    asset = upload_service.get_asset(db, asset_id)
    return MediaAssetUsagesOut(asset_id=asset.id, usages=media_delete.collect_asset_usages(db, asset))


@router.post("/admin/media/assets/{asset_id}/delete", response_model=MediaAssetDeleteOut)
def delete_media_asset(
    asset_id: str,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("upload.manage"))],
    payload: MediaAssetDeleteRequest | None = None,
):
    """Delete an unlinked uploaded asset and its owned file under MEDIA_ROOT."""
    settings = get_settings()
    require_feature("enable_uploads", settings)
    body = payload or MediaAssetDeleteRequest()
    asset = upload_service.get_asset(db, asset_id)
    result = media_delete.delete_media_asset(
        db, asset=asset, admin_id=admin.id, confirm=bool(body.confirm)
    )
    return MediaAssetDeleteOut.model_validate(result)


@router.get("/admin/media/storage-health")
def media_storage_health_report(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("upload.read"))],
    include_orphans: bool = Query(True),
):
    settings = get_settings()
    require_feature("enable_uploads", settings)
    return media_storage_health.run_storage_health_check(db, include_orphans=include_orphans)


@router.post("/admin/media/temp-cleanup", response_model=StaleTempCleanupOut)
def cleanup_stale_temp_uploads(
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("upload.manage"))],
    max_age_seconds: int = Query(86400, ge=3600, le=604800),
):
    """Remove stale ``*.part`` files under MEDIA_ROOT/temp only."""
    settings = get_settings()
    require_feature("enable_uploads", settings)
    from app.services.media_audit import record_media_event

    result = media_delete.cleanup_stale_temp_uploads(max_age_seconds=max_age_seconds)
    record_media_event(
        db,
        event_type="media_temp_cleanup",
        admin_id=admin.id,
        details=result,
    )
    db.commit()
    return StaleTempCleanupOut(**result, max_age_seconds=max_age_seconds)
