"""Generate synthetic test video and process through upload → probe → HLS encode."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from app.core.config import Settings
from app.models.admin import AdminUser
from app.models.media_assets import MediaAsset
from app.models.media_encoding import MediaPackage
from app.models.media_processing import MediaProcessingJob
from app.services.demo.ownership import DemoOwnership
from app.services.media_processing.encode_job import queue_encode_hls_job
from app.services.media_processing.jobs import queue_probe_job
from app.services.media_upload import create_upload_session, get_session, stream_upload_to_session
from app.services.storage import media_root
from app.services.streaming.activation import get_active_completed_package

logger = logging.getLogger(__name__)


def generate_synthetic_mp4(path: Path, *, duration_seconds: int = 20, tag: str = "demo") -> Path:
    """Create a small synthetic H.264/AAC 640x360 clip (no copyrighted media)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique color/tag per asset to avoid duplicate-checksum rejection across runs.
    hue = abs(hash(tag)) % 360
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=hsl({hue}\\,60%\\,35%):s=640x360:d={duration_seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=f={440 + (abs(hash(tag)) % 200)}:d={duration_seconds}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        "-metadata",
        f"title=iFilm demo {tag}",
        "-metadata",
        f"comment=ifilm-demo-{tag}",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed to generate demo clip: "
            + result.stderr.decode("utf-8", errors="replace")[-800:]
        )
    return path


async def _upload_file(
    db: Session,
    *,
    settings: Settings,
    admin: AdminUser,
    source: Path,
    filename: str,
    movie_id: int | None = None,
    episode_id: int | None = None,
    series_id: int | None = None,
    season_id: int | None = None,
) -> MediaAsset:
    data = source.read_bytes()
    session, asset = create_upload_session(
        db,
        settings=settings,
        admin_id=admin.id,
        filename=filename,
        mime_type="video/mp4",
        size_bytes=len(data),
        category="originals",
        movie_id=movie_id,
        series_id=series_id,
        season_id=season_id,
        episode_id=episode_id,
    )
    upload = UploadFile(
        file=BytesIO(data),
        filename=filename,
        size=len(data),
        headers=Headers({"content-type": "video/mp4"}),
    )
    try:
        await stream_upload_to_session(
            db,
            settings=settings,
            session=session,
            file=upload,
            upload_offset=0,
            upload_complete=True,
        )
    finally:
        await upload.close()
    session = get_session(db, session.id)
    if session.media_asset is None or session.media_asset.upload_status != "completed":
        raise RuntimeError(f"Demo upload did not complete for {filename}")
    return session.media_asset


def upload_and_encode(
    db: Session,
    *,
    settings: Settings,
    admin: AdminUser,
    ownership: DemoOwnership,
    work_dir: Path,
    label: str,
    movie_id: int | None = None,
    episode_id: int | None = None,
    series_id: int | None = None,
    season_id: int | None = None,
    duration_seconds: int = 20,
    wait_timeout_seconds: int = 600,
) -> MediaAsset:
    """Upload via real session path, queue probe+encode, wait for active package."""
    # Reuse existing completed demo asset for this owner when present.
    q = db.query(MediaAsset).filter(MediaAsset.upload_status == "completed")
    if movie_id is not None:
        q = q.filter(MediaAsset.movie_id == movie_id)
    elif episode_id is not None:
        q = q.filter(MediaAsset.episode_id == episode_id)
    else:
        raise ValueError("movie_id or episode_id required")
    existing = q.order_by(MediaAsset.created_at.desc()).first()
    if existing is not None and existing.id in set(ownership.media_asset_ids):
        package = get_active_completed_package(db, existing.id)
        if package is not None:
            if package.id not in ownership.package_ids:
                ownership.package_ids.append(package.id)
            return existing

    clip = work_dir / f"{label}.mp4"
    generate_synthetic_mp4(clip, duration_seconds=duration_seconds, tag=label)
    ownership.media_files.append(str(clip.resolve()))

    asset = asyncio.run(
        _upload_file(
            db,
            settings=settings,
            admin=admin,
            source=clip,
            filename=f"{label}.mp4",
            movie_id=movie_id,
            episode_id=episode_id,
            series_id=series_id,
            season_id=season_id,
        )
    )
    ownership.media_asset_ids.append(asset.id)
    if asset.storage_path:
        ownership.media_files.append(asset.storage_path)

    probe_job, _ = queue_probe_job(db, settings=settings, asset=asset, admin_id=admin.id)
    db.commit()
    _wait_job(db, probe_job.id, timeout_seconds=wait_timeout_seconds)

    db.refresh(asset)
    encode_job, package, _ = queue_encode_hls_job(
        db, settings=settings, asset=asset, admin_id=admin.id
    )
    if package is not None and package.id not in ownership.package_ids:
        ownership.package_ids.append(package.id)
    db.commit()
    _wait_job(db, encode_job.id, timeout_seconds=wait_timeout_seconds)

    package = get_active_completed_package(db, asset.id)
    if package is None:
        raise RuntimeError(f"HLS package was not activated for asset {asset.id}")
    if package.id not in ownership.package_ids:
        ownership.package_ids.append(package.id)

    # Confirm 240p/360p renditions for 640x360 source.
    heights = {int(r.height) for r in package.renditions if r.status == "completed"}
    if 240 not in heights or 360 not in heights:
        logger.warning(
            "Demo asset %s active package missing expected 240p/360p (have %s)",
            asset.id,
            sorted(heights),
        )
    return asset


def _wait_job(db: Session, job_id: str, *, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        db.expire_all()
        job = db.get(MediaProcessingJob, job_id)
        if job is None:
            raise RuntimeError(f"Processing job {job_id} disappeared")
        if job.status == "completed":
            return
        if job.status in {"failed", "cancelled"}:
            raise RuntimeError(
                f"Processing job {job_id} ({job.job_type}) ended as {job.status}: "
                f"{job.error_message or 'unknown'}"
            )
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for media job {job_id}")


def count_active_demo_packages(db: Session, ownership: DemoOwnership) -> int:
    if not ownership.package_ids:
        return 0
    return (
        db.query(MediaPackage)
        .filter(
            MediaPackage.id.in_(ownership.package_ids),
            MediaPackage.is_active.is_(True),
            MediaPackage.status == "completed",
        )
        .count()
    )


def demo_work_dir(settings: Settings) -> Path:
    path = media_root() / "temp" / "demo-seed"
    path.mkdir(parents=True, exist_ok=True)
    return path
