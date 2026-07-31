"""Resolve and validate completed media asset paths under MEDIA_ROOT."""

from __future__ import annotations

from pathlib import Path

from app.models.media_assets import MediaAsset
from app.services.media_processing.errors import AssetNotReadyError, PathSecurityError
from app.services.storage import media_root


def resolve_completed_asset_path(asset: MediaAsset) -> Path:
    """Return the absolute regular-file path for a completed local asset."""
    if asset.upload_status != "completed":
        raise AssetNotReadyError("Media asset upload is not completed")
    if (asset.storage_backend or "").lower() != "local":
        raise AssetNotReadyError(f"Unsupported storage backend: {asset.storage_backend}")
    if not asset.storage_path:
        raise AssetNotReadyError("Media asset has no storage path")

    root = media_root().resolve()
    raw = Path(asset.storage_path)
    candidate = raw if raw.is_absolute() else (root / raw)

    # Reject symlink components that escape MEDIA_ROOT before resolving.
    probe = candidate if candidate.is_absolute() else (root / candidate)
    if not probe.is_absolute():
        probe = root / probe
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

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise PathSecurityError("Uploaded media file is missing") from exc
    except OSError as exc:
        raise PathSecurityError("Unable to resolve media path") from exc

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PathSecurityError("Media path escapes MEDIA_ROOT") from exc

    if not resolved.is_file():
        raise PathSecurityError("Media path is not a regular file")

    return resolved
