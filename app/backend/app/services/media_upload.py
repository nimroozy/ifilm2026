"""Media upload session orchestration (local filesystem, resumable streaming, SHA256)."""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, timedelta
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.models.media_assets import MediaAsset, UploadSession, new_uuid, utcnow
from app.services.content_sniff import PROBE_BYTES, validate_content_compatibility
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
TERMINAL_STATUSES = frozenset({"completed", "cancelled", "failed"})


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found"
        )
    return session


def get_asset(db: Session, asset_id: str) -> MediaAsset:
    asset = db.get(MediaAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
    return asset


def _absolute_temp(session: UploadSession) -> Path:
    from app.services.storage import media_root

    if not session.temp_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Upload session has no temp path"
        )
    path = Path(session.temp_path)
    if not path.is_absolute():
        path = media_root() / path
    return path.resolve()


def _fail_session(db: Session, session: UploadSession, temp_path: Path | None, error: str) -> None:
    if temp_path is not None and temp_path.exists():
        temp_path.unlink(missing_ok=True)
    session.status = "failed"
    session.error = error
    if session.media_asset:
        session.media_asset.upload_status = "failed"
        session.media_asset.checksum_sha256 = None
        db.add(session.media_asset)
    db.add(session)
    db.commit()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


async def _finalize_session(
    db: Session,
    *,
    settings: Settings,
    session: UploadSession,
    temp_path: Path,
) -> UploadSession:
    size = session.bytes_received
    if size != session.expected_size_bytes:
        _fail_session(
            db,
            session,
            temp_path,
            f"Incomplete upload: received {size} bytes, expected {session.expected_size_bytes}",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Incomplete upload: received {size} bytes, expected {session.expected_size_bytes}"
            ),
        )

    # Re-validate content from the start of the assembled temp file.
    with temp_path.open("rb") as handle:
        prefix = handle.read(PROBE_BYTES)
    validate_content_compatibility(
        prefix=prefix,
        extension=file_extension(session.media_asset.original_filename),
        declared_mime=session.media_asset.mime_type,
    )

    checksum = _sha256_file(temp_path)
    asset = session.media_asset
    if settings.upload_reject_duplicate_checksum:
        existing = (
            db.query(MediaAsset)
            .filter(
                MediaAsset.checksum_sha256 == checksum,
                MediaAsset.upload_status == "completed",
            )
            .first()
        )
        if existing is not None:
            _fail_session(db, session, temp_path, "Duplicate upload checksum")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate completed upload with identical checksum",
            )

    final_path = asset_storage_path(
        category=asset.category,
        asset_id=asset.id,
        stored_filename=asset.stored_filename,
    )

    try:
        # Move first so a failed unique insert does not leave orphans in category dirs.
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
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        session = get_session(db, session.id)
        if final_path.exists():
            final_path.unlink(missing_ok=True)
        _fail_session(db, session, None, "Duplicate upload checksum")
        # Partial unique index is the concurrency-safe backstop.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate completed upload with identical checksum",
        ) from exc

    db.refresh(session)
    if session.media_asset_id:
        db.refresh(session.media_asset)
    return session


async def stream_upload_to_session(
    db: Session,
    *,
    settings: Settings,
    session: UploadSession,
    file: UploadFile,
    upload_offset: int,
    upload_complete: bool,
) -> UploadSession:
    if session.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Session is {session.status}"
        )
    if _is_expired(session.expires_at):
        temp = None
        try:
            temp = _absolute_temp(session)
        except HTTPException:
            temp = None
        _fail_session(db, session, temp, "Upload session expired")
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Upload session expired")

    if upload_offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Upload-Offset must be >= 0"
        )
    if upload_offset != session.bytes_received:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Upload-Offset mismatch: client sent {upload_offset}, "
                f"server expects {session.bytes_received}"
            ),
        )

    if file.filename:
        sanitize_upload_filename(file.filename)
    if file.content_type:
        validate_upload_content_type(file.content_type, settings.upload_allowed_content_types)

    temp_path = _absolute_temp(session)
    temp_path.parent.mkdir(parents=True, exist_ok=True)

    # Fresh write vs append.
    if upload_offset == 0:
        mode = "wb"
        if session.status not in {"pending", "uploading"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=f"Session is {session.status}"
            )
    else:
        mode = "ab"
        if not temp_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot resume: temporary upload file is missing; restart with Upload-Offset 0",
            )

    session.status = "uploading"
    session.media_asset.upload_status = "uploading"
    db.add(session)
    db.add(session.media_asset)
    db.commit()

    written = 0
    probe = bytearray()
    try:
        async with aiofiles.open(temp_path, mode) as out:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                # Always measure from the request start offset + bytes written in
                # this request. Do not add session.bytes_received here — mid-upload
                # progress flushes update that field and would double-count.
                next_total = upload_offset + written + len(chunk)
                if next_total > settings.upload_max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail="File too large"
                    )
                if next_total > session.expected_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Uploaded size exceeds declared size_bytes",
                    )
                if upload_offset == 0 and len(probe) < PROBE_BYTES:
                    need = PROBE_BYTES - len(probe)
                    probe.extend(chunk[:need])
                await out.write(chunk)
                written += len(chunk)
                if (upload_offset + written) % (8 * CHUNK_SIZE) == 0:
                    session.bytes_received = upload_offset + written
                    db.add(session)
                    db.commit()
    except HTTPException as exc:
        # Mid-chunk hard failures discard progress for this request when starting fresh;
        # for append failures keep prior committed offset by truncating this request's bytes.
        if upload_offset == 0:
            _fail_session(db, session, temp_path, str(exc.detail))
        else:
            # Truncate file back to the pre-request offset.
            if temp_path.exists():
                with temp_path.open("rb+") as handle:
                    handle.truncate(upload_offset)
            session.bytes_received = upload_offset
            db.add(session)
            db.commit()
        raise

    except Exception as exc:  # noqa: BLE001
        if upload_offset == 0:
            _fail_session(db, session, temp_path, "Upload failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload failed"
        ) from exc

    session.bytes_received = upload_offset + written
    db.add(session)
    db.commit()

    # Size incompleteness takes precedence over signature checks when the client
    # marks the upload complete — never finalize or store a checksum for a short body.
    if upload_complete and session.bytes_received != session.expected_size_bytes:
        _fail_session(
            db,
            session,
            temp_path,
            (
                f"Incomplete upload: received {session.bytes_received} bytes, "
                f"expected {session.expected_size_bytes}"
            ),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Incomplete upload: received {session.bytes_received} bytes, "
                f"expected {session.expected_size_bytes}"
            ),
        )

    # Sniff on the first segment once we have a useful prefix, or when size is exact.
    if upload_offset == 0 and probe:
        if len(probe) >= 12 or session.bytes_received == session.expected_size_bytes:
            try:
                validate_content_compatibility(
                    prefix=bytes(probe),
                    extension=file_extension(session.media_asset.original_filename),
                    declared_mime=session.media_asset.mime_type,
                )
            except HTTPException as exc:
                _fail_session(db, session, temp_path, str(exc.detail))
                raise

    if session.bytes_received == session.expected_size_bytes:
        return await _finalize_session(db, settings=settings, session=session, temp_path=temp_path)

    # Partial chunk accepted; client may resume with Upload-Offset = bytes_received.
    db.refresh(session)
    return session


def cancel_upload_session(db: Session, session: UploadSession) -> UploadSession:
    if session.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Completed uploads cannot be cancelled"
        )
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
