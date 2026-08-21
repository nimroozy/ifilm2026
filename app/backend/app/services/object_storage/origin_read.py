"""Token-gated origin read fallback for HLS playlists and segments.

Fetches object bytes from central origin only after normal playback-session
authorization. Never returns permanent object URLs, bucket names, or credentials.
Relative playlist rewrite stays on ``/api/stream/{token}/…``.
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from app.core.config import Settings, get_settings
from app.models.media_encoding import MediaPackage
from app.services.object_storage.factory import get_central_origin_storage
from app.services.object_storage.keys import ObjectKeyBuilder
from app.services.object_storage.package_sync import ORIGIN_SYNC_STATUS_SYNCED
from app.services.streaming.paths import _LABEL_RE, _SEGMENT_RE, StreamPathError

logger = logging.getLogger(__name__)

_REL_SAFE = re.compile(r"^[A-Za-z0-9._/-]+$")


def origin_hls_read_fallback_enabled(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return bool(cfg.enable_object_storage and cfg.enable_origin_hls_read_fallback)


def package_allows_origin_read(package: MediaPackage) -> bool:
    return (
        package.origin_sync_status == ORIGIN_SYNC_STATUS_SYNCED
        and bool(package.origin_object_prefix)
        and package.status == "completed"
        and bool(package.is_active)
    )


def _require_safe_relative(relative_path: str) -> str:
    rel = (relative_path or "").replace("\\", "/").strip().lstrip("/")
    if not rel or ".." in rel.split("/") or rel.startswith("/"):
        raise StreamPathError("traversal_rejected", "Path traversal rejected")
    if not _REL_SAFE.fullmatch(rel):
        raise StreamPathError("invalid_segment", "Unsafe relative path")
    return rel


def logical_master_relative() -> str:
    return "master.m3u8"


def logical_variant_relative(label: str) -> str:
    if not _LABEL_RE.fullmatch(label):
        raise StreamPathError("invalid_label", "Invalid rendition label")
    return f"{label}/index.m3u8"


def logical_segment_relative(label: str, segment_name: str) -> str:
    if not _LABEL_RE.fullmatch(label):
        raise StreamPathError("invalid_label", "Invalid rendition label")
    if not _SEGMENT_RE.fullmatch(segment_name):
        raise StreamPathError("invalid_segment", "Unsupported or invalid segment name")
    return f"{label}/{segment_name}"


def fetch_package_object_bytes(
    package: MediaPackage,
    relative_path: str,
    *,
    settings: Settings | None = None,
) -> bytes:
    """Download one package-relative object from origin into memory via a temp file."""
    cfg = settings or get_settings()
    if not origin_hls_read_fallback_enabled(cfg):
        raise StreamPathError("origin_fallback_disabled", "Origin read fallback disabled")
    if not package_allows_origin_read(package):
        raise StreamPathError("origin_not_synced", "Package is not synced to origin")

    rel = _require_safe_relative(relative_path)
    # Enforce rendition membership for nested paths (same as local delivery).
    if "/" in rel:
        label = rel.split("/", 1)[0]
        known = {item.label for item in (package.renditions or [])}
        if known and label not in known and rel != "master.m3u8":
            raise StreamPathError("unknown_rendition", "Rendition not part of this package")

    keys = ObjectKeyBuilder(prefix=cfg.media_object_key_prefix or "ifilm")
    key = keys.package_object_key(
        asset_id=package.media_asset_id,
        package_id=package.id,
        relative_path=rel,
    )
    # Defense in depth: key must stay under this package's origin prefix.
    expected_prefix = package.origin_object_prefix or keys.package_root(
        asset_id=package.media_asset_id, package_id=package.id
    )
    if not key.startswith(expected_prefix.rstrip("/") + "/"):
        raise StreamPathError("escape_rejected", "Object key escapes package prefix")

    storage = get_central_origin_storage(cfg)
    try:
        with tempfile.NamedTemporaryFile(prefix="ifilm-origin-", suffix=".bin", delete=True) as tmp:
            dest = Path(tmp.name)
            storage.get_file(key=key, destination=dest)
            data = dest.read_bytes()
    except FileNotFoundError as exc:
        raise StreamPathError("not_found", "Origin object not found") from exc
    except Exception as exc:  # noqa: BLE001 — map provider errors without leaking secrets
        logger.warning(
            "origin_hls_read_failed",
            extra={"package_id": package.id, "relative_path": rel, "error_type": type(exc).__name__},
        )
        raise StreamPathError("origin_read_failed", "Origin object read failed") from exc
    return data
