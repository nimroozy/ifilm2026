"""Safe admin deletion of uploaded media assets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.content import Episode, Movie
from app.models.media_assets import MediaAsset
from app.models.media_encoding import MediaPackage
from app.models.media_processing import MediaProcessingJob
from app.services.media_audit import record_media_event
from app.services.storage import artwork_root, media_root

OWNED_CATEGORIES = frozenset({"originals", "posters", "backdrops", "trailers", "subtitles"})


def _safe_resolve_under(root: Path, relative_or_abs: str) -> Path | None:
    """Resolve a stored path under root; return None if it escapes or is invalid."""
    raw = Path(relative_or_abs)
    candidate = raw if raw.is_absolute() else (root / raw)
    try:
        if not raw.is_absolute():
            current = root.resolve()
            for part in Path(relative_or_abs).parts:
                if part in {"", "."}:
                    continue
                if part == "..":
                    return None
                current = current / part
            resolved = current.resolve(strict=False)
        else:
            resolved = candidate.resolve(strict=False)
        resolved.relative_to(root.resolve())
        return resolved
    except (OSError, ValueError):
        return None


def collect_asset_usages(db: Session, asset: MediaAsset) -> list[dict[str, Any]]:
    usages: list[dict[str, Any]] = []
    if asset.movie_id is not None:
        movie = db.get(Movie, asset.movie_id)
        label = movie.title if movie else f"#{asset.movie_id}"
        usages.append(
            {
                "kind": "movie",
                "id": asset.movie_id,
                "label": label,
                "status": getattr(movie, "status", None),
            }
        )
    if asset.episode_id is not None:
        episode = db.get(Episode, asset.episode_id)
        label = episode.title if episode else f"#{asset.episode_id}"
        usages.append(
            {
                "kind": "episode",
                "id": asset.episode_id,
                "label": label,
                "status": getattr(episode, "status", None),
            }
        )
    if asset.series_id is not None:
        usages.append({"kind": "series", "id": asset.series_id, "label": f"#{asset.series_id}"})
    if asset.season_id is not None:
        usages.append({"kind": "season", "id": asset.season_id, "label": f"#{asset.season_id}"})

    packages = (
        db.query(MediaPackage)
        .filter(MediaPackage.media_asset_id == asset.id)
        .order_by(MediaPackage.created_at.desc())
        .limit(20)
        .all()
    )
    for pkg in packages:
        usages.append(
            {
                "kind": "package",
                "id": pkg.id,
                "label": pkg.package_type,
                "status": pkg.status,
                "is_active": bool(pkg.is_active),
            }
        )

    jobs = (
        db.query(MediaProcessingJob)
        .filter(MediaProcessingJob.media_asset_id == asset.id)
        .order_by(MediaProcessingJob.created_at.desc())
        .limit(20)
        .all()
    )
    for job in jobs:
        usages.append(
            {
                "kind": "processing_job",
                "id": job.id,
                "label": job.job_type,
                "status": job.status,
            }
        )
    return usages


def assert_asset_deletable(db: Session, asset: MediaAsset) -> list[dict[str, Any]]:
    if asset.upload_status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
    if (asset.source_type or "uploaded") == "external":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="External media assets are detached, not deleted via file delete",
        )
    usages = collect_asset_usages(db, asset)
    blocking = [
        u
        for u in usages
        if u["kind"] in {"movie", "episode", "series", "season"}
        or (u["kind"] == "package" and u.get("is_active"))
        or (u["kind"] == "processing_job" and u.get("status") in {"queued", "running", "claimed"})
    ]
    if blocking or any(u["kind"] in {"movie", "episode", "series", "season"} for u in usages):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "media_in_use",
                "message": "Media asset is linked or in use; unlink/archive first",
                "usages": usages,
            },
        )
    return usages


def delete_media_asset(
    db: Session,
    *,
    asset: MediaAsset,
    admin_id: int,
    confirm: bool,
) -> dict[str, Any]:
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required to delete media asset",
        )
    usages = assert_asset_deletable(db, asset)
    if asset.category not in OWNED_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported media category for deletion: {asset.category}",
        )

    root = media_root().resolve()
    art_root = artwork_root().resolve()
    removed_file = False
    storage_key = asset.storage_path

    if storage_key:
        path = _safe_resolve_under(root, storage_key)
        if path is None:
            # Artwork categories may historically live under ARTWORK_ROOT — still require containment.
            path = _safe_resolve_under(art_root, storage_key)
        if path is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Storage path is outside owned media roots",
            )
        if path.exists():
            if path.is_file():
                path.unlink()
                removed_file = True
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Refusing to delete non-file storage path",
                )
            # Remove empty asset directory under category/<asset_id>/
            parent = path.parent
            try:
                if parent.is_dir() and parent.name == asset.id and not any(parent.iterdir()):
                    parent.rmdir()
            except OSError:
                pass

    # Soft-delete DB row markers; keep id for audit joinability.
    asset.upload_status = "deleted"
    asset.processing_status = "none"
    asset.storage_path = None
    asset.checksum_sha256 = None
    db.add(asset)
    record_media_event(
        db,
        event_type="media_asset_deleted",
        admin_id=admin_id,
        media_asset_id=asset.id,
        details={
            "category": asset.category,
            "storage_key": storage_key,
            "removed_file": removed_file,
            "prior_usages": usages,
            "original_filename": asset.original_filename,
        },
    )
    db.commit()
    return {
        "id": asset.id,
        "deleted": True,
        "removed_file": removed_file,
        "upload_status": asset.upload_status,
    }


def cleanup_stale_temp_uploads(*, max_age_seconds: int = 86400) -> dict[str, int]:
    """Remove stale ``*.part`` files under MEDIA_ROOT/temp only."""
    from datetime import UTC, datetime

    temp_dir = media_root() / "temp"
    if not temp_dir.is_dir():
        return {"scanned": 0, "removed": 0}
    now = datetime.now(UTC).timestamp()
    scanned = 0
    removed = 0
    for path in temp_dir.glob("*.part"):
        scanned += 1
        try:
            age = now - path.stat().st_mtime
            if age < max_age_seconds:
                continue
            # Containment check
            resolved = path.resolve()
            resolved.relative_to(temp_dir.resolve())
            if resolved.is_file():
                resolved.unlink()
                removed += 1
        except (OSError, ValueError):
            continue
    return {"scanned": scanned, "removed": removed}
