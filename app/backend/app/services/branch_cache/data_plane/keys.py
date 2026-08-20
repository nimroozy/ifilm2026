"""Immutable cache key mapping and relative-path sanitization."""

from __future__ import annotations

import re
from urllib.parse import unquote

from app.services.branch_cache.data_plane.errors import CODE_PATH, CODE_TRAVERSAL, DataPlaneError
from app.services.object_storage.keys import ObjectKeyBuilder

_SAFE_SEG = re.compile(r"^[A-Za-z0-9._-]+$")
_ALLOWED_SUFFIXES = frozenset({".m3u8", ".ts", ".vtt", ".m4s", ".mp4", ".aac"})


def normalize_relative_path(raw: str) -> str:
    """Normalize a package-relative path; reject traversal and encoding tricks."""
    text = (raw or "").replace("\\", "/").strip()
    if not text:
        raise DataPlaneError("empty path", code=CODE_PATH)
    # Reject URL-encoded traversal before and after decode.
    if "%2e" in text.lower() or "%2f" in text.lower() or "%5c" in text.lower():
        decoded = unquote(text)
        if ".." in decoded.split("/") or decoded.startswith("/") and ".." in decoded:
            raise DataPlaneError("encoded traversal rejected", code=CODE_TRAVERSAL)
        text = decoded.replace("\\", "/")
    text = text.lstrip("/")
    if not text or text.startswith("/") or "\\" in text:
        raise DataPlaneError("invalid path", code=CODE_PATH)
    parts = text.split("/")
    if any(p in {"", ".", ".."} for p in parts):
        raise DataPlaneError("traversal rejected", code=CODE_TRAVERSAL)
    for part in parts:
        if not _SAFE_SEG.match(part):
            raise DataPlaneError("unsafe path segment", code=CODE_PATH)
    lower = text.lower()
    if not any(lower.endswith(suf) for suf in _ALLOWED_SUFFIXES):
        raise DataPlaneError("unsupported object type", code=CODE_PATH)
    return text


def grant_path_for_relative(path_prefix: str, relative_path: str) -> str:
    """Build the absolute grant path used for path_prefix binding checks."""
    prefix = (path_prefix or "").strip()
    if not prefix.startswith("/"):
        prefix = f"/{prefix}"
    if not prefix.endswith("/"):
        prefix = f"{prefix}/"
    rel = normalize_relative_path(relative_path)
    return f"{prefix}{rel}"


def origin_object_key(
    *,
    asset_id: str,
    package_id: str,
    relative_path: str,
    key_prefix: str = "ifilm",
) -> str:
    rel = normalize_relative_path(relative_path)
    return ObjectKeyBuilder(prefix=key_prefix).package_object_key(
        asset_id=asset_id, package_id=package_id, relative_path=rel
    )


def content_type_for(relative_path: str) -> str:
    lower = relative_path.lower()
    if lower.endswith(".m3u8"):
        return "application/vnd.apple.mpegurl"
    if lower.endswith(".ts") or lower.endswith(".m4s"):
        return "video/mp2t"
    if lower.endswith(".vtt"):
        return "text/vtt"
    if lower.endswith(".mp4"):
        return "video/mp4"
    if lower.endswith(".aac"):
        return "audio/aac"
    return "application/octet-stream"
