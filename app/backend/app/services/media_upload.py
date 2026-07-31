"""Media upload session orchestration (local filesystem, streaming, SHA256)."""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, timedelta
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.models.media_assets import MediaAsset, UploadSession, new_uuid, utcnow
from app.services.storage import (
    asset_storage_path,
    ensure_media_layout,
    relative_media_path,
    temp_upload_dir,
)
from app.services.uploads import (
    file_extension,
    reject_oversized,
    reject_zero_byte_size,
    sanitize_upload_filename,
    validate_upload_content_type,
)

SESSION_TTL = timedelta(hours=24)
CHUNK_SIZE = 1024 * 1024


def _is_expired(expires_at) -> bool:
    if expires_at is None:
        return False
    now = utcnow()
    aware = expires_at if expires_at.tzinfo is not None else expires_at.replace(tzinfo=UTC)
    return aware < now


def progress_percent(session: UploadSession) -> int:
    if session.expected_size_bytes <= 0:
        return 0
    return min(100, int((session.bytes_received * 100) / session.expected_size_bytes))


def session_out_dict(session: UploadSession, *, include_asset: bool = True) -> dict:
    payload: dict = {
        "id": session.id,
        "media_asset_id": session.media_asset_id,
        "expected_size_bytes": session.expected_size_bytes,
        "bytes_received": session.bytes_received,
        "status": session.status,
        "progress_percent": progress_percent(session),
        "error": session.error,
        "expires_at": session.expires_at,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "media_asset": None,
    }
    if include_asset and session.media_asset is not None:
        payload["media_asset"] = session.media_asset
    return payload


def create_upload_session(
    db: Session,
    *,
    settings: Settings,
    admin_id: int,
    filename: str,
    mime_type: str,
    size_bytes: int,
    category: str,
    movie_id: int | None,
    series_id: int | None,
    season_id: int | None,
    episode_id: int | None,
) -> tuple[UploadSession, MediaAsset]:
    ensure_media_layout()
    safe_name = sanitize_upload_filename(filename)
    reject_zero_byte_size(size_bytes)
    reject_oversized(size_bytes, settings.upload_max_bytes)
    validated_mime = validate_upload_content_type(mime_type, settings.upload_allowed_content_types)
    ext = file_extension(safe_name)

    asset_id = new_uuid()
    stored_filename = f"{asset_id}{ext}" if ext else asset_id
    asset = MediaAsset(
        id=asset_id,
        movie_id=movie_id,
        series_id=series_id,
        season_id=season_id,
        episode_id=episode_id,
        original_filename=safe_name,
        stored_filename=stored_filename,
        mime_type=validated_mime,
        extension=ext.lstrip(".") if ext else "",
        size_bytes=0,
        storage_backend="local",
        category=category,
        upload_status="pending",
        processing_status="none",
        created_by_admin_id=admin_id,
    )
    session = UploadSession(
        id=new_uuid(),
        media_asset_id=asset_id,
        expected_size_bytes=size_bytes,
        bytes_received=0,
        status="pending",
        created_by_admin_id=admin_id,
        expires_at=utcnow() + SESSION_TTL,
    )
    temp_path = temp_upload_dir() / f"{session.id}.part"
    session.temp_path = relative_media_path(temp_path)

    db.add(asset)
    db.flush()
    db.add(session)
    db.commit()
    db.refresh(asset)
    db.refresh(session)
    session.media_asset = asset
    return session, asset


def get_session(db: Session, session_id: str) -> UploadSession:
    session = (
        db.query(UploadSession)
        .options(joinedload(UploadSession.media_asset))
        .filter(UploadSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found")
    return session


def get_asset(db: Session, asset_id: str) -> MediaAsset:
    asset = db.get(MediaAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
    return asset


def _absolute_temp(session: UploadSession) -> Path:
    from app.services.storage import media_root

    if not session.temp_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload session has no temp path")
    path = Path(session.temp_path)
    if not path.is_absolute():
        path = media_root() / path
    return path.resolve()


def _find_duplicate_checksum(db: Session, checksum: str, *, exclude_asset_id: str) -> MediaAsset | None:
    return (
        db.query(MediaAsset)
        .filter(
            MediaAsset.checksum_sha256 == checksum,
            MediaAsset.upload_status == "completed",
            MediaAsset.id != exclude_asset_id,
        )
        .first()
    )


async def stream_upload_to_session(
    db: Session,
    *,
    settings: Settings,
    session: UploadSession,
    file: UploadFile,
) -> UploadSession:
    if session.status in {"completed", "cancelled", "failed"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Session is {session.status}")
    if _is_expired(session.expires_at):
        session.status = "failed"
        session.error = "Upload session expired"
        session.media_asset.upload_status = "failed"
        db.add(session)
        db.add(session.media_asset)
        db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Upload session expired")

    # Validate declared mime against allowed list (filename already sanitized at create).
    if file.filename:
        sanitize_upload_filename(file.filename)
    if file.content_type:
        validate_upload_content_type(file.content_type, settings.upload_allowed_content_types)

    temp_path = _absolute_temp(session)
    temp_path.parent.mkdir(parents=True, exist_ok=True)

    session.status = "uploading"
    session.media_asset.upload_status = "uploading"
    session.bytes_received = 0
    db.add(session)
    db.add(session.media_asset)
    db.commit()

    digest = hashlib.sha256()
    size = 0
    try:
        async with aiofiles.open(temp_path, "wb") as out:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.upload_max_bytes:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large")
                if size > session.expected_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Uploaded size exceeds declared size_bytes",
                    )
                digest.update(chunk)
                await out.write(chunk)
                session.bytes_received = size
                # Periodic progress flush for GET progress polling.
                if size == chunk or size % (8 * CHUNK_SIZE) == 0:
                    db.add(session)
                    db.commit()
    except HTTPException as exc:
        _fail_session(db, session, temp_path, str(exc.detail))
        raise
    except Exception as exc:  # noqa: BLE001 — mark failed then re-raise as 500
        _fail_session(db, session, temp_path, "Upload failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload failed") from exc

    if size <= 0:
        _fail_session(db, session, temp_path, "Zero-byte files are not allowed")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Zero-byte files are not allowed")

    checksum = digest.hexdigest()
    if settings.upload_reject_duplicate_checksum:
        duplicate = _find_duplicate_checksum(db, checksum, exclude_asset_id=session.media_asset_id)
        if duplicate is not None:
            _fail_session(db, session, temp_path, "Duplicate upload checksum")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate completed upload with identical checksum",
            )

    asset = session.media_asset
    final_path = asset_storage_path(
        category=asset.category,
        asset_id=asset.id,
        stored_filename=asset.stored_filename,
    )
    shutil.move(str(temp_path), str(final_path))

    asset.size_bytes = size
    asset.checksum_sha256 = checksum
    asset.storage_path = relative_media_path(final_path)
    asset.storage_backend = "local"
    asset.upload_status = "completed"
    asset.processing_status = "none"
    session.bytes_received = size
    session.status = "completed"
    session.error = None
    session.temp_path = None
    db.add(asset)
    db.add(session)
    db.commit()
    db.refresh(session)
    db.refresh(asset)
    session.media_asset = asset
    return session


def _fail_session(db: Session, session: UploadSession, temp_path: Path, error: str) -> None:
    if temp_path.exists():
        temp_path.unlink(missing_ok=True)
    session.status = "failed"
    session.error = error
    if session.media_asset:
        session.media_asset.upload_status = "failed"
        db.add(session.media_asset)
    db.add(session)
    db.commit()


def cancel_upload_session(db: Session, session: UploadSession) -> UploadSession:
    if session.status == "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Completed uploads cannot be cancelled")
    if session.status == "cancelled":
        return session

    try:
        temp_path = _absolute_temp(session)
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
    except HTTPException:
        pass

    session.status = "cancelled"
    session.error = "Cancelled by administrator"
    if session.media_asset and session.media_asset.upload_status != "completed":
        session.media_asset.upload_status = "cancelled"
        db.add(session.media_asset)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session
