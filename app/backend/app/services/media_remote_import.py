"""Server-to-server remote MP4 import into protected local MEDIA_ROOT.

HLS mirroring is deferred to a later milestone — validate rejects HLS for import.
External Source (unprotected direct) remains a separate attach path.
"""

from __future__ import annotations

import errno
import hashlib
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.content import Episode, Movie
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.models.media_processing import (
    JOB_TYPE_REMOTE_MEDIA_IMPORT,
    MediaProcessingJob,
)
from app.models.remote_media_import import RemoteMediaImport
from app.services.content_sniff import PROBE_BYTES, validate_content_compatibility
from app.services.integration_secrets import (
    IntegrationSecretsError,
    decrypt_secret,
    encrypt_secret,
)
from app.services.media_external import (
    ExternalMediaError,
    assert_safe_external_url,
    validate_external_media_url,
)
from app.services.media_external_attach import mask_external_url
from app.services.media_processing.jobs import add_job_event, clip_diagnostic
from app.services.storage import asset_storage_path, media_category_dir, relative_media_path

logger = logging.getLogger("app.media_remote_import")

SAFE_UA = "iFilm-RemoteMediaImport/1.0"
DESTINATION_LOCAL = "local_origin"
PHASE_QUEUED = "queued"
PHASE_VALIDATING = "validating"
PHASE_CONNECTING = "connecting"
PHASE_DOWNLOADING = "downloading"
PHASE_VERIFYING = "verifying"
PHASE_COMPLETED = "completed"
PHASE_FAILED = "failed"
PHASE_CANCELLED = "cancelled"
TERMINAL_PHASES = frozenset({PHASE_COMPLETED, PHASE_FAILED, PHASE_CANCELLED})


class RemoteImportError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True)
class RemoteImportValidationOut:
    url_display: str
    host: str
    kind: str
    content_type: str | None
    content_length: int | None
    accept_ranges: bool
    https_ok: bool
    within_size_limit: bool
    estimated_disk_ok: bool


def _require_secrets_key(settings: Settings) -> str:
    key = (settings.integration_secrets_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INTEGRATION_SECRETS_KEY must be configured for remote media import",
        )
    return key


def encrypt_source_url(url: str, settings: Settings) -> bytes:
    try:
        return encrypt_secret(plaintext=url, master_key=_require_secrets_key(settings))
    except IntegrationSecretsError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to encrypt source URL",
        ) from exc


def decrypt_source_url(ciphertext: bytes, settings: Settings) -> str:
    try:
        return decrypt_secret(ciphertext=ciphertext, master_key=_require_secrets_key(settings))
    except IntegrationSecretsError as exc:
        raise RemoteImportError("decrypt_failed", "Unable to decrypt source URL") from exc


def _disk_free_bytes(path: Path) -> int:
    usage = shutil.disk_usage(path)
    return int(usage.free)


def validate_remote_import_url(url: str, *, settings: Settings) -> RemoteImportValidationOut:
    """Validate URL for import — MP4 only; reuses SSRF policy from media_external."""
    try:
        result = validate_external_media_url(url)
    except ExternalMediaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result.kind != "mp4":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HLS import is deferred; only direct MP4 URLs are supported for Import from URL",
        )
    max_bytes = int(settings.remote_import_max_bytes)
    within = result.content_length is None or result.content_length <= max_bytes
    if result.content_length is not None and result.content_length > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source file is larger than configured import limit",
        )
    category_dir = media_category_dir("originals")
    free = _disk_free_bytes(category_dir)
    reserve = int(settings.remote_import_disk_reserve_bytes)
    needed = (result.content_length or 0) + reserve
    disk_ok = free >= needed if result.content_length is not None else free > reserve
    if result.content_length is not None and not disk_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient destination storage for this import",
        )
    _, host = assert_safe_external_url(result.url)
    return RemoteImportValidationOut(
        url_display=mask_external_url(result.url) or "[redacted]",
        host=host,
        kind=result.kind,
        content_type=result.content_type,
        content_length=result.content_length,
        accept_ranges=result.accept_ranges,
        https_ok=True,
        within_size_limit=within,
        estimated_disk_ok=disk_ok,
    )


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path or ""
    name = Path(path).name or "remote-import.mp4"
    if not name.lower().endswith(".mp4"):
        name = f"{name}.mp4" if "." not in name else name
    # Keep filesystem-safe basename
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)[:180]
    return safe or "remote-import.mp4"


def _owner_exists(db: Session, owner_type: str, owner_id: int) -> None:
    if owner_type == "movie":
        if db.query(Movie).filter(Movie.id == owner_id).first() is None:
            raise HTTPException(status_code=404, detail="Movie not found")
    elif owner_type == "episode":
        if db.query(Episode).filter(Episode.id == owner_id).first() is None:
            raise HTTPException(status_code=404, detail="Episode not found")
    else:
        raise HTTPException(status_code=400, detail="owner_type must be movie or episode")


def find_active_owner_import(
    db: Session, *, owner_type: str, owner_id: int
) -> RemoteMediaImport | None:
    return (
        db.query(RemoteMediaImport)
        .filter(
            RemoteMediaImport.owner_type == owner_type,
            RemoteMediaImport.owner_id == owner_id,
            RemoteMediaImport.phase.notin_(tuple(TERMINAL_PHASES)),
        )
        .first()
    )


def queue_remote_media_import(
    db: Session,
    *,
    settings: Settings,
    url: str,
    owner_type: str,
    owner_id: int,
    destination: str,
    admin_id: int | None,
) -> tuple[MediaProcessingJob, RemoteMediaImport, MediaAsset]:
    if not settings.enable_remote_media_import and not settings.enable_uploads:
        raise HTTPException(status_code=403, detail="Remote media import is disabled")
    if destination != DESTINATION_LOCAL:
        raise HTTPException(
            status_code=400,
            detail="Only protected local origin destination is supported in this milestone",
        )
    _owner_exists(db, owner_type, owner_id)
    validation = validate_remote_import_url(url, settings=settings)
    # Re-normalize via assert (already validated) for encryption payload.
    normalized, host = assert_safe_external_url(url)

    existing = find_active_owner_import(db, owner_type=owner_type, owner_id=owner_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="An import is already in progress for this title",
        )

    asset_id = new_uuid()
    stored_name = f"{asset_id[:8]}_{_filename_from_url(normalized)}"
    asset = MediaAsset(
        id=asset_id,
        movie_id=owner_id if owner_type == "movie" else None,
        episode_id=owner_id if owner_type == "episode" else None,
        original_filename=_filename_from_url(normalized),
        stored_filename=stored_name,
        mime_type=validation.content_type or "video/mp4",
        extension=".mp4",
        size_bytes=0,
        storage_backend="local",
        category="originals",
        upload_status="uploading",
        processing_status="none",
        source_type="remote_import",
    )
    db.add(asset)
    db.flush()

    max_attempts = max(1, int(settings.remote_import_max_attempts))
    job = MediaProcessingJob(
        id=new_uuid(),
        media_asset_id=asset.id,
        job_type=JOB_TYPE_REMOTE_MEDIA_IMPORT,
        status="queued",
        priority=50,
        max_attempts=max_attempts,
        progress_percent=0,
        current_step=PHASE_QUEUED,
        created_by_admin_id=admin_id,
    )
    db.add(job)
    db.flush()

    record = RemoteMediaImport(
        id=new_uuid(),
        processing_job_id=job.id,
        media_asset_id=asset.id,
        owner_type=owner_type,
        owner_id=owner_id,
        destination=destination,
        phase=PHASE_QUEUED,
        source_url_ciphertext=encrypt_source_url(normalized, settings),
        source_url_display=validation.url_display,
        source_host=host,
        content_type=validation.content_type,
        content_length=validation.content_length,
        accept_ranges=validation.accept_ranges,
        total_bytes=validation.content_length,
        created_by_admin_id=admin_id,
    )
    db.add(record)
    add_job_event(
        db,
        job,
        "queued",
        message="Remote MP4 import queued",
        details={
            "source_display": validation.url_display,
            "host": host,
            "destination": destination,
            "content_length": validation.content_length,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An import is already in progress for this title",
        ) from exc
    db.refresh(job)
    db.refresh(record)
    db.refresh(asset)
    logger.info(
        "remote_import_queued job_id=%s asset_id=%s owner=%s/%s host=%s admin_id=%s",
        job.id,
        asset.id,
        owner_type,
        owner_id,
        host,
        admin_id,
    )
    return job, record, asset


def remote_import_public(record: RemoteMediaImport, job: MediaProcessingJob | None = None) -> dict[str, Any]:
    """Secret-free status DTO — never includes raw source URL."""
    return {
        "id": record.id,
        "job_id": record.processing_job_id,
        "media_asset_id": record.media_asset_id,
        "owner_type": record.owner_type,
        "owner_id": record.owner_id,
        "destination": record.destination,
        "phase": record.phase,
        "status": job.status if job is not None else record.phase,
        "source_url_display": record.source_url_display,
        "source_host": record.source_host,
        "content_type": record.content_type,
        "content_length": record.content_length,
        "accept_ranges": record.accept_ranges,
        "bytes_downloaded": record.bytes_downloaded,
        "total_bytes": record.total_bytes,
        "progress_percent": record.progress_percent,
        "transfer_rate_bps": record.transfer_rate_bps,
        "eta_seconds": record.eta_seconds,
        "checksum_sha256": record.checksum_sha256,
        "retry_count": record.retry_count,
        "error_code": record.error_code or (job.error_code if job else None),
        "error_message": record.error_message or (job.error_message if job else None),
        "transfer_started_at": record.transfer_started_at.isoformat()
        if record.transfer_started_at
        else None,
        "transfer_finished_at": record.transfer_finished_at.isoformat()
        if record.transfer_finished_at
        else None,
        "cancel_requested": bool(job.cancel_requested) if job else False,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def get_remote_import(db: Session, import_id: str) -> tuple[RemoteMediaImport, MediaProcessingJob]:
    record = db.query(RemoteMediaImport).filter(RemoteMediaImport.id == import_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Remote import not found")
    job = db.query(MediaProcessingJob).filter(MediaProcessingJob.id == record.processing_job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    return record, job


def request_cancel_remote_import(db: Session, import_id: str) -> dict[str, Any]:
    record, job = get_remote_import(db, import_id)
    if record.phase in TERMINAL_PHASES or job.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Import is already finished")
    job.cancel_requested = True
    db.add(job)
    add_job_event(db, job, "cancel_requested", message="Cancel requested by admin")
    db.commit()
    db.refresh(record)
    db.refresh(job)
    return remote_import_public(record, job)


def retry_remote_import(db: Session, *, settings: Settings, import_id: str) -> dict[str, Any]:
    record, job = get_remote_import(db, import_id)
    if job.status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Only failed or cancelled imports can be retried")
    if find_active_owner_import(db, owner_type=record.owner_type, owner_id=record.owner_id):
        raise HTTPException(status_code=409, detail="An import is already in progress for this title")

    part_path = _part_path_for_asset(record.media_asset_id)
    can_resume = bool(record.accept_ranges) and part_path.exists() and part_path.stat().st_size > 0
    if not can_resume and part_path.exists():
        part_path.unlink(missing_ok=True)

    job.status = "queued"
    job.cancel_requested = False
    job.error_code = None
    job.error_message = None
    job.progress_percent = min(int(record.progress_percent or 0), 99) if can_resume else 0
    job.current_step = PHASE_QUEUED
    job.finished_at = None
    job.started_at = None
    job.next_retry_at = None
    job.worker_id = None
    record.phase = PHASE_QUEUED
    if can_resume:
        record.bytes_downloaded = int(part_path.stat().st_size)
    else:
        record.bytes_downloaded = 0
        record.progress_percent = 0
    record.transfer_rate_bps = None
    record.eta_seconds = None
    record.error_code = None
    record.error_message = None
    record.transfer_started_at = None
    record.transfer_finished_at = None
    record.retry_count = int(record.retry_count or 0) + 1
    asset = db.query(MediaAsset).filter(MediaAsset.id == record.media_asset_id).first()
    if asset is not None:
        asset.upload_status = "uploading"
        asset.processing_status = "none"
        db.add(asset)
    db.add(job)
    db.add(record)
    add_job_event(
        db,
        job,
        "requeued",
        message="Remote import requeued",
        details={"resume": can_resume, "bytes": record.bytes_downloaded},
    )
    db.commit()
    db.refresh(record)
    db.refresh(job)
    return remote_import_public(record, job)


def _fsync_path(path: Path) -> None:
    with path.open("rb+") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _durable_move(src: Path, dest: Path) -> None:
    """Atomic replace when possible; EXDEV-safe copy+fsync+unlink across bind mounts."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(str(src), str(dest))
        return
    except OSError as exc:
        if getattr(exc, "errno", None) != errno.EXDEV:
            raise
    with src.open("rb") as in_f, dest.open("wb") as out_f:
        shutil.copyfileobj(in_f, out_f, length=1024 * 1024)
        out_f.flush()
        os.fsync(out_f.fileno())
    _fsync_path(dest)
    src.unlink(missing_ok=True)


_CONTENT_RANGE_RE = re.compile(
    r"^bytes\s+(\d+)-(\d+)/(\d+|\*)\s*$", re.IGNORECASE
)


def _parse_content_range(header: str | None) -> tuple[int, int, int | None] | None:
    if not header:
        return None
    match = _CONTENT_RANGE_RE.match(header.strip())
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    total = None if match.group(3) == "*" else int(match.group(3))
    return start, end, total


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _part_path_for_asset(asset_id: str) -> Path:
    from app.services.storage import media_root

    return media_root() / "temp" / f"remote-import-{asset_id}.part"


def _update_progress(
    db: Session,
    record: RemoteMediaImport,
    job: MediaProcessingJob,
    *,
    settings: Settings,
    bytes_downloaded: int,
    total_bytes: int | None,
    started_monotonic: float,
    force: bool = False,
) -> None:
    now = datetime.now(UTC)
    last = record.last_progress_at
    interval = float(settings.remote_import_progress_interval_seconds)
    if (
        not force
        and last is not None
        and (now - last).total_seconds() < interval
        and bytes_downloaded - int(record.bytes_downloaded or 0) < 8 * 1024 * 1024
    ):
        return
    elapsed = max(0.001, time.monotonic() - started_monotonic)
    rate = int(bytes_downloaded / elapsed)
    eta = None
    percent = 0
    if total_bytes and total_bytes > 0:
        percent = min(99, int(bytes_downloaded * 100 / total_bytes))
        remaining = max(0, total_bytes - bytes_downloaded)
        eta = int(remaining / rate) if rate > 0 else None
    record.bytes_downloaded = bytes_downloaded
    record.total_bytes = total_bytes
    record.progress_percent = percent
    record.transfer_rate_bps = rate
    record.eta_seconds = eta
    record.last_progress_at = now
    record.phase = PHASE_DOWNLOADING
    job.progress_percent = percent
    job.current_step = PHASE_DOWNLOADING
    job.heartbeat_at = now
    db.add(record)
    db.add(job)
    db.commit()


def execute_remote_media_import(
    db: Session,
    *,
    settings: Settings,
    job: MediaProcessingJob,
) -> None:
    """Worker entry: stream remote MP4 to a .part file, verify, atomic finalize."""
    record = (
        db.query(RemoteMediaImport)
        .filter(RemoteMediaImport.processing_job_id == job.id)
        .first()
    )
    if record is None:
        job.status = "failed"
        job.error_code = "missing_import_row"
        job.error_message = "Remote import state missing"
        job.finished_at = utcnow()
        db.add(job)
        db.commit()
        return

    asset = db.query(MediaAsset).filter(MediaAsset.id == record.media_asset_id).first()
    if asset is None:
        _fail(db, job, record, "missing_asset", "Media asset missing")
        return

    part_path: Path | None = None
    try:
        if job.cancel_requested:
            _cancel(db, job, record, asset, part_path)
            return

        record.phase = PHASE_VALIDATING
        job.current_step = PHASE_VALIDATING
        db.add(record)
        db.add(job)
        db.commit()

        raw_url = decrypt_source_url(record.source_url_ciphertext, settings)
        # DNS rebinding defense: re-validate before connect.
        normalized, _host = assert_safe_external_url(raw_url)
        validation = validate_external_media_url(normalized)
        if validation.kind != "mp4":
            raise RemoteImportError("unsupported_type", "Only MP4 remote import is supported")

        max_bytes = int(settings.remote_import_max_bytes)
        total = validation.content_length
        if total is not None and total > max_bytes:
            raise RemoteImportError("too_large", "Source file is larger than configured import limit")

        category_dir = media_category_dir("originals")
        free = _disk_free_bytes(category_dir)
        reserve = int(settings.remote_import_disk_reserve_bytes)
        if total is not None and free < total + reserve:
            raise RemoteImportError("insufficient_storage", "Insufficient destination storage")

        from app.services.storage import media_root

        part_path = media_root() / "temp" / f"remote-import-{asset.id}.part"
        part_path.parent.mkdir(parents=True, exist_ok=True)

        resume_from = 0
        digest = hashlib.sha256()
        if (
            bool(record.accept_ranges or validation.accept_ranges)
            and part_path.exists()
            and part_path.stat().st_size > 0
        ):
            resume_from = int(part_path.stat().st_size)
            # Rebuild digest over verified partial bytes before appending.
            with part_path.open("rb") as prior:
                while True:
                    block = prior.read(1024 * 1024)
                    if not block:
                        break
                    digest.update(block)
        elif part_path.exists():
            part_path.unlink()

        record.phase = PHASE_CONNECTING
        record.transfer_started_at = utcnow()
        record.accept_ranges = validation.accept_ranges
        record.content_type = validation.content_type
        record.content_length = validation.content_length
        record.total_bytes = total
        if resume_from > 0:
            record.bytes_downloaded = resume_from
        job.current_step = PHASE_CONNECTING
        db.add(record)
        db.add(job)
        db.commit()

        timeout = httpx.Timeout(
            float(settings.remote_import_connect_timeout) + float(settings.remote_import_read_timeout),
            connect=float(settings.remote_import_connect_timeout),
            read=float(settings.remote_import_read_timeout),
        )
        chunk_size = max(64 * 1024, int(settings.remote_import_chunk_bytes))
        downloaded = resume_from
        started = time.monotonic()
        last_byte_at = time.monotonic()
        stall_limit = float(settings.remote_import_stall_timeout)

        headers = {"User-Agent": SAFE_UA, "Accept": "*/*"}

        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            max_redirects=0,
            headers=headers,
            verify=True,
        ) as client:
            # Re-check SSRF immediately before GET (DNS rebinding defense).
            assert_safe_external_url(normalized)
            req_headers = dict(headers)
            if resume_from > 0 and validation.accept_ranges:
                req_headers["Range"] = f"bytes={resume_from}-"
            with client.stream("GET", normalized, headers=req_headers) as response:
                if response.is_redirect:
                    raise RemoteImportError("redirect_rejected", "External media redirects are not allowed")
                if resume_from > 0 and response.status_code == 200:
                    # Server ignored Range — restart cleanly rather than append corrupt data.
                    resume_from = 0
                    downloaded = 0
                    digest = hashlib.sha256()
                    if part_path.exists():
                        part_path.unlink()
                elif resume_from > 0 and response.status_code == 206:
                    parsed_range = _parse_content_range(response.headers.get("content-range"))
                    if parsed_range is None or parsed_range[0] != resume_from:
                        raise RemoteImportError(
                            "resume_failed",
                            "Invalid Content-Range for resumed download",
                            retryable=True,
                        )
                    if parsed_range[2] is not None:
                        total = parsed_range[2]
                        record.total_bytes = total
                elif resume_from > 0:
                    raise RemoteImportError(
                        "resume_failed",
                        f"Expected HTTP 206 for resume, got {response.status_code}",
                        retryable=True,
                    )
                elif response.status_code >= 400:
                    raise RemoteImportError(
                        "http_error",
                        f"Source returned HTTP {response.status_code}",
                        retryable=response.status_code >= 500,
                    )

                length_hdr = response.headers.get("content-length")
                if total is None and length_hdr and length_hdr.isdigit():
                    total = int(length_hdr) + resume_from
                    record.total_bytes = total

                record.phase = PHASE_DOWNLOADING
                job.current_step = PHASE_DOWNLOADING
                db.add(record)
                db.add(job)
                db.commit()

                mode = "ab" if resume_from > 0 else "wb"
                with part_path.open(mode) as out:
                    for chunk in response.iter_bytes(chunk_size=chunk_size):
                        if not chunk:
                            if time.monotonic() - last_byte_at > stall_limit:
                                raise RemoteImportError(
                                    "transfer_stalled", "Transfer stalled", retryable=True
                                )
                            continue
                        # Refresh cancel flag
                        db.refresh(job)
                        if job.cancel_requested:
                            _cancel(db, job, record, asset, part_path)
                            return
                        out.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                        last_byte_at = time.monotonic()
                        if downloaded > max_bytes:
                            raise RemoteImportError(
                                "too_large", "Source file is larger than configured import limit"
                            )
                        _update_progress(
                            db,
                            record,
                            job,
                            settings=settings,
                            bytes_downloaded=downloaded,
                            total_bytes=total,
                            started_monotonic=started,
                        )
                    out.flush()
                    os.fsync(out.fileno())

        if total is not None and downloaded != total:
            raise RemoteImportError(
                "size_mismatch",
                f"Downloaded {downloaded} bytes, expected {total}",
                retryable=True,
            )

        record.phase = PHASE_VERIFYING
        job.current_step = PHASE_VERIFYING
        job.progress_percent = 99
        db.add(record)
        db.add(job)
        db.commit()

        _fsync_path(part_path)
        with part_path.open("rb") as handle:
            prefix = handle.read(PROBE_BYTES)
        validate_content_compatibility(
            prefix=prefix,
            extension=".mp4",
            declared_mime=record.content_type or "video/mp4",
        )
        checksum = digest.hexdigest()
        final_path = asset_storage_path(
            category=asset.category,
            asset_id=asset.id,
            stored_filename=asset.stored_filename,
        )
        _durable_move(part_path, final_path)
        _fsync_path(final_path)
        part_path = None

        asset.size_bytes = downloaded
        asset.checksum_sha256 = checksum
        asset.storage_path = relative_media_path(final_path)
        asset.storage_backend = "local"
        asset.upload_status = "completed"
        asset.processing_status = "none"
        # Treat as local uploaded original so protected pipeline eligibility applies.
        asset.source_type = "uploaded"
        asset.mime_type = record.content_type or "video/mp4"

        record.phase = PHASE_COMPLETED
        record.bytes_downloaded = downloaded
        record.progress_percent = 100
        record.checksum_sha256 = checksum
        record.transfer_finished_at = utcnow()
        record.error_code = None
        record.error_message = None

        job.status = "completed"
        job.progress_percent = 100
        job.current_step = PHASE_COMPLETED
        job.finished_at = utcnow()
        job.error_code = None
        job.error_message = None

        db.add(asset)
        db.add(record)
        db.add(job)
        add_job_event(
            db,
            job,
            "completed",
            message="Remote MP4 import completed",
            details={
                "bytes": downloaded,
                "checksum": checksum[:12],
                "source_display": record.source_url_display,
            },
        )
        db.commit()
        logger.info(
            "remote_import_completed job_id=%s asset_id=%s bytes=%s host=%s",
            job.id,
            asset.id,
            downloaded,
            record.source_host,
        )
    except RemoteImportError as exc:
        _fail(
            db,
            job,
            record,
            exc.code,
            str(exc),
            asset=asset,
            part_path=part_path,
            retryable=exc.retryable,
            keep_partial=exc.retryable and bool(record.accept_ranges),
        )
    except ExternalMediaError as exc:
        _fail(db, job, record, exc.code, str(exc), asset=asset, part_path=part_path)
    except Exception:  # noqa: BLE001
        logger.exception("remote_import_failed job_id=%s", job.id)
        _fail(
            db,
            job,
            record,
            "import_failed",
            "Remote import failed",
            asset=asset,
            part_path=part_path,
            retryable=True,
            keep_partial=bool(record.accept_ranges),
        )


def _cleanup_part(part_path: Path | None) -> None:
    if part_path is not None and part_path.exists():
        part_path.unlink(missing_ok=True)


def _fail(
    db: Session,
    job: MediaProcessingJob,
    record: RemoteMediaImport,
    code: str,
    message: str,
    *,
    asset: MediaAsset | None = None,
    part_path: Path | None = None,
    retryable: bool = False,
    keep_partial: bool = False,
) -> None:
    if not keep_partial:
        _cleanup_part(part_path)
    elif part_path is not None and part_path.exists():
        # Persist verified partial size for Accept-Ranges resume.
        try:
            record.bytes_downloaded = int(part_path.stat().st_size)
        except OSError:
            pass
    safe_message = clip_diagnostic(message) or "Remote import failed"
    # Never persist raw URLs in error text
    if record.source_url_display and record.source_url_display in safe_message:
        pass
    record.phase = PHASE_FAILED
    record.error_code = code
    record.error_message = safe_message
    record.transfer_finished_at = utcnow()
    job.status = "failed"
    job.error_code = code
    job.error_message = safe_message
    job.finished_at = utcnow()
    job.current_step = PHASE_FAILED
    if asset is not None:
        asset.upload_status = "failed"
        db.add(asset)
    db.add(record)
    db.add(job)
    add_job_event(db, job, "failed", message=safe_message, details={"code": code, "retryable": retryable})
    db.commit()


def _cancel(
    db: Session,
    job: MediaProcessingJob,
    record: RemoteMediaImport,
    asset: MediaAsset,
    part_path: Path | None,
) -> None:
    _cleanup_part(part_path)
    record.phase = PHASE_CANCELLED
    record.error_code = "cancelled"
    record.error_message = "Import cancelled"
    record.transfer_finished_at = utcnow()
    job.status = "cancelled"
    job.error_code = "cancelled"
    job.error_message = "Import cancelled"
    job.finished_at = utcnow()
    job.current_step = PHASE_CANCELLED
    asset.upload_status = "cancelled"
    db.add(asset)
    db.add(record)
    db.add(job)
    add_job_event(db, job, "cancelled", message="Import cancelled")
    db.commit()
