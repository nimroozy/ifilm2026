"""Admin/ops media storage consistency checks (read-only; no auto-delete)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.media_assets import MediaAsset
from app.models.media_processing import MediaProcessingJob
from app.services.media_processing.mount_health import media_processing_readiness
from app.services.storage import MEDIA_SUBDIRS, ensure_media_layout, media_root

OWNED_CATEGORIES = ("originals", "posters", "backdrops", "trailers", "subtitles")


def _path_for_asset(root: Path, asset: MediaAsset) -> Path | None:
    if not asset.storage_path:
        return None
    raw = Path(asset.storage_path)
    if any(part == ".." for part in raw.parts):
        return None
    candidate = raw if raw.is_absolute() else (root / raw)
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root.resolve())
        return resolved
    except (OSError, ValueError):
        return None


def run_storage_health_check(db: Session, *, include_orphans: bool = True) -> dict[str, Any]:
    ensure_media_layout()
    root = media_root().resolve()
    mounts = media_processing_readiness()

    assets = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.upload_status == "completed",
            MediaAsset.source_type == "uploaded",
        )
        .all()
    )

    healthy: list[dict[str, Any]] = []
    missing_files: list[dict[str, Any]] = []
    size_mismatches: list[dict[str, Any]] = []
    bad_paths: list[dict[str, Any]] = []
    known_files: set[Path] = set()

    for asset in assets:
        path = _path_for_asset(root, asset)
        if path is None:
            bad_paths.append(
                {
                    "asset_id": asset.id,
                    "category": asset.category,
                    "storage_key": asset.storage_path,
                    "reason": "path_escape_or_invalid",
                }
            )
            continue
        known_files.add(path)
        if not path.exists() or not path.is_file():
            missing_files.append(
                {
                    "asset_id": asset.id,
                    "category": asset.category,
                    "storage_key": asset.storage_path,
                    "expected_size": asset.size_bytes,
                    "checksum_sha256": asset.checksum_sha256,
                }
            )
            continue
        actual_size = path.stat().st_size
        if asset.size_bytes and actual_size != asset.size_bytes:
            size_mismatches.append(
                {
                    "asset_id": asset.id,
                    "category": asset.category,
                    "storage_key": asset.storage_path,
                    "expected_size": asset.size_bytes,
                    "actual_size": actual_size,
                }
            )
            continue
        healthy.append(
            {
                "asset_id": asset.id,
                "category": asset.category,
                "storage_key": asset.storage_path,
                "size_bytes": actual_size,
            }
        )

    orphan_files: list[dict[str, Any]] = []
    if include_orphans:
        for category in OWNED_CATEGORIES:
            cat_dir = root / category
            if not cat_dir.is_dir():
                continue
            for path in cat_dir.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    path.resolve().relative_to(root)
                except ValueError:
                    continue
                if path in known_files:
                    continue
                # Skip temp leftovers mistakenly nested (shouldn't happen)
                orphan_files.append(
                    {
                        "category": category,
                        "relative_path": str(path.relative_to(root)),
                        "size_bytes": path.stat().st_size,
                    }
                )

    # Duplicate hashes among completed assets
    dup_rows = (
        db.query(MediaAsset.checksum_sha256, func.count(MediaAsset.id))
        .filter(
            MediaAsset.upload_status == "completed",
            MediaAsset.checksum_sha256.isnot(None),
        )
        .group_by(MediaAsset.checksum_sha256)
        .having(func.count(MediaAsset.id) > 1)
        .all()
    )
    duplicate_hashes: list[dict[str, Any]] = []
    for checksum, count in dup_rows:
        ids = [
            a.id
            for a in db.query(MediaAsset)
            .filter(
                MediaAsset.checksum_sha256 == checksum,
                MediaAsset.upload_status == "completed",
            )
            .all()
        ]
        duplicate_hashes.append({"checksum_sha256": checksum, "count": count, "asset_ids": ids})

    failed_probes = (
        db.query(MediaProcessingJob)
        .filter(
            MediaProcessingJob.job_type == "probe",
            MediaProcessingJob.status == "failed",
        )
        .order_by(MediaProcessingJob.created_at.desc())
        .limit(50)
        .all()
    )
    stuck_uploads = (
        db.query(MediaAsset)
        .filter(MediaAsset.upload_status.in_(("pending", "uploading")))
        .order_by(MediaAsset.updated_at.desc())
        .limit(50)
        .all()
    )

    summary = {
        "healthy": len(healthy),
        "missing_files": len(missing_files),
        "size_mismatches": len(size_mismatches),
        "bad_paths": len(bad_paths),
        "orphan_files": len(orphan_files),
        "duplicate_hashes": len(duplicate_hashes),
        "failed_probes": len(failed_probes),
        "stuck_uploads": len(stuck_uploads),
    }
    return {
        "ok": summary["missing_files"] == 0
        and summary["size_mismatches"] == 0
        and summary["bad_paths"] == 0
        and bool(mounts.get("media_processing_ready")),
        "summary": summary,
        "mounts": mounts,
        "media_root_relative_layout": list(MEDIA_SUBDIRS),
        "missing_files": missing_files[:100],
        "size_mismatches": size_mismatches[:100],
        "bad_paths": bad_paths[:100],
        "orphan_files": orphan_files[:100],
        "duplicate_hashes": duplicate_hashes[:50],
        "failed_probes": [
            {
                "job_id": j.id,
                "asset_id": j.media_asset_id,
                "error_code": j.error_code,
                "error_message": j.error_message,
            }
            for j in failed_probes
        ],
        "stuck_uploads": [
            {
                "asset_id": a.id,
                "upload_status": a.upload_status,
                "category": a.category,
                "original_filename": a.original_filename,
            }
            for a in stuck_uploads
        ],
        # Intentionally omit full healthy list when large — counts only.
        "healthy_sample": healthy[:20],
    }
