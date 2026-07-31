"""Queue and execute encode_hls jobs (local HLS VOD packages)."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.models.media_encoding import MediaPackage, MediaRendition, PACKAGE_TYPE_HLS_VOD
from app.models.media_processing import (
    ACTIVE_JOB_STATUSES,
    JOB_TYPE_ENCODE_HLS,
    MediaProcessingJob,
)
from app.services.media_processing.errors import (
    PROGRESS_COMPLETED,
    PROGRESS_ENCODING,
    PROGRESS_PROMOTING,
    PROGRESS_QUEUED,
    PROGRESS_VALIDATING,
    PROGRESS_VALIDATING_PACKAGE,
    PROGRESS_WRITING_PLAYLISTS,
    EncodeCancelledError,
    MediaProcessingError,
    PermanentProcessingError,
    ProbeCancelledError,
    ProbeRequiredError,
)
from app.services.media_processing.hls_encode import encode_hls_renditions, file_sha256
from app.services.media_processing.jobs import (
    _fail_or_retry,
    add_job_event,
    clip_diagnostic,
)
from app.services.media_processing.package_paths import (
    final_package_dir,
    promote_work_to_final,
    relative_or_raise,
    remove_tree_if_exists,
    work_package_dir,
)
from app.services.media_processing.paths import resolve_completed_asset_path
from app.services.media_processing.profiles import select_profiles_for_source
from app.services.media_processing.validation import validate_hls_package
from app.services.storage import media_root, relative_media_path


def _clip(message: str | None) -> str | None:
    return clip_diagnostic(message)


def find_active_encode_job(db: Session, asset_id: str) -> MediaProcessingJob | None:
    return (
        db.query(MediaProcessingJob)
        .filter(
            MediaProcessingJob.media_asset_id == asset_id,
            MediaProcessingJob.job_type == JOB_TYPE_ENCODE_HLS,
            MediaProcessingJob.status.in_(tuple(ACTIVE_JOB_STATUSES)),
        )
        .first()
    )


def get_package(db: Session, package_id: str) -> MediaPackage:
    package = (
        db.query(MediaPackage)
        .options(
            joinedload(MediaPackage.renditions),
            joinedload(MediaPackage.media_asset),
        )
        .filter(MediaPackage.id == package_id)
        .first()
    )
    if not package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media package not found")
    return package


def list_packages_for_asset(db: Session, asset_id: str) -> list[MediaPackage]:
    return (
        db.query(MediaPackage)
        .options(joinedload(MediaPackage.renditions))
        .filter(MediaPackage.media_asset_id == asset_id)
        .order_by(MediaPackage.created_at.desc())
        .all()
    )


def list_encoding_profiles(db: Session) -> list:
    from app.models.media_encoding import MediaEncodingProfile

    return (
        db.query(MediaEncodingProfile)
        .order_by(MediaEncodingProfile.sort_order.asc(), MediaEncodingProfile.height.asc())
        .all()
    )


def queue_encode_hls_job(
    db: Session,
    *,
    settings: Settings,
    asset: MediaAsset,
    admin_id: int | None,
) -> tuple[MediaProcessingJob, MediaPackage, bool]:
    """Create a queued encode_hls job + pending package. Returns (job, package, created)."""
    if asset.upload_status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="HLS encode requires a completed upload",
        )
    if (asset.storage_backend or "").lower() != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported storage backend for processing",
        )
    if asset.probed_at is None or not asset.height or not asset.width:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Successful probe required before HLS encoding",
        )

    existing = find_active_encode_job(db, asset.id)
    if existing is not None:
        package = (
            db.query(MediaPackage)
            .filter(MediaPackage.processing_job_id == existing.id)
            .first()
        )
        if package is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active HLS encode job already exists",
            )
        return existing, package, False

    profiles = select_profiles_for_source(
        db, settings=settings, source_height=int(asset.height)
    )
    if not profiles:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No encoding profiles fit source resolution (never upscale)",
        )

    job = MediaProcessingJob(
        id=new_uuid(),
        media_asset_id=asset.id,
        job_type=JOB_TYPE_ENCODE_HLS,
        status="queued",
        priority=200,
        attempt_count=0,
        max_attempts=settings.media_processing_max_attempts,
        progress_percent=PROGRESS_QUEUED,
        current_step="queued",
        queued_at=utcnow(),
        created_by_admin_id=admin_id,
    )
    package = MediaPackage(
        id=new_uuid(),
        media_asset_id=asset.id,
        processing_job_id=job.id,
        package_type=PACKAGE_TYPE_HLS_VOD,
        status="pending",
        source_width=asset.width,
        source_height=asset.height,
        duration_seconds=asset.duration_seconds,
        segment_duration_seconds=settings.hls_segment_duration_seconds,
        rendition_count=0,
        created_by_admin_id=admin_id,
    )
    try:
        db.add(job)
        db.flush()
        package.processing_job_id = job.id
        db.add(package)
        add_job_event(db, job, "queued", "HLS encode job queued")
        asset.processing_status = "queued"
        db.add(asset)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = find_active_encode_job(db, asset.id)
        if existing is not None:
            package = (
                db.query(MediaPackage)
                .filter(MediaPackage.processing_job_id == existing.id)
                .first()
            )
            if package is not None:
                return existing, package, False
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Active HLS encode job already exists",
        ) from None
    db.refresh(job)
    db.refresh(package)
    return job, package, True


def _package_for_job(db: Session, job: MediaProcessingJob) -> MediaPackage | None:
    return (
        db.query(MediaPackage)
        .options(joinedload(MediaPackage.renditions))
        .filter(MediaPackage.processing_job_id == job.id)
        .first()
    )


def _mark_package_failed(
    db: Session,
    package: MediaPackage | None,
    *,
    error_code: str,
    message: str,
    cancelled: bool = False,
) -> None:
    if package is None:
        return
    package.status = "cancelled" if cancelled else "failed"
    package.error_code = error_code
    package.error_message = _clip(message)
    if package.work_path:
        remove_tree_if_exists(media_root() / package.work_path)
    package.work_path = None
    db.add(package)


def execute_encode_hls_job(
    db: Session, *, settings: Settings, job: MediaProcessingJob
) -> MediaProcessingJob:
    asset = job.media_asset or db.get(MediaAsset, job.media_asset_id)
    package = _package_for_job(db, job)

    def cancel_check() -> bool:
        db.refresh(job)
        return bool(job.cancel_requested)

    if asset is None:
        _fail_or_retry(
            db,
            settings=settings,
            job=job,
            error_code="asset_missing",
            message="Media asset missing",
            transient=False,
        )
        _mark_package_failed(db, package, error_code="asset_missing", message="Media asset missing")
        db.commit()
        db.refresh(job)
        return job

    try:
        job.progress_percent = PROGRESS_VALIDATING
        job.current_step = "validating_source"
        if package is not None:
            package.status = "encoding"
            package.error_code = None
            package.error_message = None
            db.add(package)
        db.add(job)
        db.commit()

        if asset.probed_at is None or not asset.height or not asset.width:
            raise ProbeRequiredError("Successful probe required before HLS encoding")

        path = resolve_completed_asset_path(asset)
        checksum_before = file_sha256(path)
        size_before = path.stat().st_size

        profiles = select_profiles_for_source(
            db, settings=settings, source_height=int(asset.height)
        )
        if not profiles:
            raise PermanentProcessingError(
                "No encoding profiles fit source resolution", code="no_profiles"
            )

        if cancel_check():
            raise EncodeCancelledError("Encode cancelled")

        work_dir = work_package_dir(job.id)
        if package is not None:
            package.work_path = relative_or_raise(work_dir)
            package.source_width = asset.width
            package.source_height = asset.height
            package.duration_seconds = asset.duration_seconds
            db.add(package)
            db.commit()

        has_audio = bool(asset.audio_stream_count and asset.audio_stream_count > 0)

        job.progress_percent = PROGRESS_ENCODING
        job.current_step = "encoding_hls"
        job.heartbeat_at = utcnow()
        db.add(job)
        db.commit()

        last_heartbeat = [0.0]

        def on_progress(index: int, total: int, snapshot: dict[str, str]) -> None:
            # Map out_time_ms into discrete job progress across renditions.
            out_ms = snapshot.get("out_time_ms") or snapshot.get("out_time_us")
            duration = float(asset.duration_seconds or 0) * 1000.0
            frac = 0.0
            if out_ms and duration > 0:
                try:
                    # out_time_us is microseconds in some ffmpeg builds when key is out_time_us
                    raw = float(out_ms)
                    if snapshot.get("out_time_us") and "out_time_ms" not in snapshot:
                        raw = raw / 1000.0
                    frac = min(1.0, max(0.0, raw / duration))
                except ValueError:
                    frac = 0.0
            overall = (index + frac) / max(total, 1)
            percent = PROGRESS_ENCODING + int(overall * (PROGRESS_WRITING_PLAYLISTS - PROGRESS_ENCODING))
            job.progress_percent = min(PROGRESS_WRITING_PLAYLISTS - 1, max(PROGRESS_ENCODING, percent))
            job.current_step = f"encoding_{profiles[index].label}"
            job.heartbeat_at = utcnow()
            # Throttle commits via attempt counter on heartbeat seconds
            import time

            now = time.monotonic()
            if now - last_heartbeat[0] >= float(settings.media_processing_heartbeat_seconds):
                last_heartbeat[0] = now
                db.add(job)
                db.commit()

        encoded = encode_hls_renditions(
            settings=settings,
            source=path,
            work_dir=work_dir,
            profiles=profiles,
            source_width=int(asset.width),
            source_height=int(asset.height),
            frame_rate=asset.video_frame_rate,
            duration_seconds=asset.duration_seconds,
            has_audio=has_audio,
            cancel_check=cancel_check,
            on_rendition_progress=on_progress,
        )

        if path.stat().st_size != size_before or file_sha256(path) != checksum_before:
            raise PermanentProcessingError(
                "Source media file changed during encode", code="source_changed"
            )

        job.progress_percent = PROGRESS_WRITING_PLAYLISTS
        job.current_step = "writing_playlists"
        job.heartbeat_at = utcnow()
        db.add(job)
        db.commit()

        job.progress_percent = PROGRESS_VALIDATING_PACKAGE
        job.current_step = "validating_package"
        if package is not None:
            package.status = "validating"
            db.add(package)
        db.add(job)
        db.commit()

        master, validated = validate_hls_package(
            work_dir,
            expected_labels=[item.label for item in encoded],
            source_height=int(asset.height),
            rendition_heights={item.label: item.height for item in encoded},
            rendition_widths={item.label: item.width for item in encoded},
            rendition_bandwidths={item.label: item.bandwidth for item in encoded},
        )

        if cancel_check():
            raise EncodeCancelledError("Encode cancelled")

        job.progress_percent = PROGRESS_PROMOTING
        job.current_step = "promoting_package"
        if package is not None:
            package.status = "promoting"
            db.add(package)
        db.add(job)
        db.commit()

        package_id = package.id if package is not None else new_uuid()
        final_dir = final_package_dir(asset.id, package_id)
        promoted = promote_work_to_final(work_dir, final_dir)

        if package is not None:
            # Replace any prior incomplete rendition rows for this package.
            for old in list(package.renditions or []):
                db.delete(old)
            db.flush()
            for item in validated:
                encoded_item = next(e for e in encoded if e.label == item.label)
                db.add(
                    MediaRendition(
                        id=new_uuid(),
                        package_id=package.id,
                        profile_id=encoded_item.profile.id,
                        label=item.label,
                        height=item.height,
                        width=item.width,
                        bandwidth=item.bandwidth,
                        average_bandwidth=item.bandwidth,
                        playlist_path=relative_media_path(item.playlist_path),
                        segment_count=item.segment_count,
                        video_codec="h264",
                        audio_codec="aac" if has_audio else None,
                        status="completed",
                    )
                )
            package.status = "completed"
            package.storage_path = relative_media_path(promoted)
            package.master_playlist_path = relative_media_path(master if master.parent == promoted else promoted / "master.m3u8")
            # After rename, master path is under final dir.
            package.master_playlist_path = relative_media_path(promoted / "master.m3u8")
            package.work_path = None
            package.rendition_count = len(validated)
            package.completed_at = utcnow()
            package.error_code = None
            package.error_message = None
            db.add(package)

        asset.processing_status = "completed"
        job.status = "completed"
        job.progress_percent = PROGRESS_COMPLETED
        job.current_step = "completed"
        job.finished_at = utcnow()
        job.heartbeat_at = utcnow()
        job.error_code = None
        job.error_message = None
        add_job_event(
            db,
            job,
            "completed",
            "HLS encode completed",
            {
                "package_id": package_id,
                "renditions": [item.label for item in validated],
                "master_playlist": relative_media_path(promoted / "master.m3u8"),
            },
        )
        db.add(asset)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    except (EncodeCancelledError, ProbeCancelledError) as exc:
        job.cancel_requested = True
        if package is not None:
                remove_tree_if_exists(work_package_dir(job.id, create=False))
            _mark_package_failed(
                db,
                package,
                error_code=getattr(exc, "code", "cancelled"),
                message=str(exc),
                cancelled=True,
            )
        _fail_or_retry(
            db,
            settings=settings,
            job=job,
            error_code=getattr(exc, "code", "cancelled"),
            message=str(exc),
            transient=False,
        )
        db.commit()
        db.refresh(job)
        return job
    except MediaProcessingError as exc:
        remove_tree_if_exists(work_package_dir(job.id, create=False))
        _mark_package_failed(
            db,
            package,
            error_code=exc.code,
            message=str(exc),
            cancelled=False,
        )
        _fail_or_retry(
            db,
            settings=settings,
            job=job,
            error_code=exc.code,
            message=str(exc),
            transient=bool(exc.transient),
        )
        db.commit()
        db.refresh(job)
        return job
    except Exception:  # noqa: BLE001
        remove_tree_if_exists(work_package_dir(job.id, create=False))
        _mark_package_failed(
            db,
            package,
            error_code="internal_error",
            message="Unexpected encoding failure",
        )
        _fail_or_retry(
            db,
            settings=settings,
            job=job,
            error_code="internal_error",
            message="Unexpected encoding failure",
            transient=False,
        )
        db.commit()
        db.refresh(job)
        return job
