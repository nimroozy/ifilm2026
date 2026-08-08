"""Resolve and validate completed media asset paths under MEDIA_ROOT."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from app.models.media_assets import MediaAsset
from app.services.media_processing.errors import (
    AssetNotReadyError,
    FileMissingPermanentError,
    PathSecurityError,
)
from app.services.storage import media_root

logger = logging.getLogger("app.media_processing.paths")

# Bounded visibility retries for NFS/bind-mount propagation races only.
_MISSING_RETRY_ATTEMPTS = 3
_MISSING_RETRY_DELAY_SECONDS = 0.35


def resolve_completed_asset_path(
    asset: MediaAsset,
    *,
    allow_transient_missing: bool = True,
) -> Path:
    """Return the absolute regular-file path for a completed local asset."""
    if asset.upload_status not in {"completed", "stored"}:
        raise AssetNotReadyError("Media asset upload is not completed")
    if (asset.storage_backend or "").lower() != "local":
        raise AssetNotReadyError(f"Unsupported storage backend: {asset.storage_backend}")
    if not asset.storage_path:
        raise AssetNotReadyError("Media asset has no storage path")

    root = media_root().resolve()
    raw = Path(asset.storage_path)
    candidate = raw if raw.is_absolute() else (root / raw)

    # Reject symlink components that escape MEDIA_ROOT before resolving.
    try:
        # Build path step-by-step under root when relative.
        if not raw.is_absolute():
            current = root
            for part in Path(asset.storage_path).parts:
                if part in {"", "."}:
                    continue
                if part == "..":
                    raise PathSecurityError("Media path escapes MEDIA_ROOT")
                current = current / part
                if current.is_symlink():
                    target = current.resolve()
                    try:
                        target.relative_to(root)
                    except ValueError as exc:
                        raise PathSecurityError("Symlink escapes MEDIA_ROOT") from exc
    except PathSecurityError:
        raise

    attempts = _MISSING_RETRY_ATTEMPTS if allow_transient_missing else 1
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            resolved = candidate.resolve(strict=True)
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise PathSecurityError("Media path escapes MEDIA_ROOT") from exc
            if not resolved.is_file():
                raise PathSecurityError("Media path is not a regular file")
            if asset.size_bytes and resolved.stat().st_size != asset.size_bytes:
                logger.warning(
                    "media_size_mismatch asset_id=%s category=%s expected=%s actual=%s",
                    asset.id,
                    asset.category,
                    asset.size_bytes,
                    resolved.stat().st_size,
                )
            return resolved
        except FileNotFoundError as exc:
            last_exc = exc
            logger.warning(
                "media_file_missing asset_id=%s category=%s storage_key=%s expected_size=%s attempt=%s/%s",
                asset.id,
                asset.category,
                asset.storage_path,
                asset.size_bytes,
                attempt,
                attempts,
            )
            if attempt < attempts:
                time.sleep(_MISSING_RETRY_DELAY_SECONDS)
                continue
        except OSError as exc:
            raise PathSecurityError("Unable to resolve media path") from exc

    # Bounded in-process retries exhausted — fail permanently so the job does not loop forever.
    raise FileMissingPermanentError(
        "Uploaded media file is missing",
        code="file_missing",
    ) from last_exc
