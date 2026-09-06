"""Central authenticated origin reads for CDN nodes (CDN-P1).

Resolves package-relative HLS objects from the local package tree first and,
when enabled, from the durable object-storage origin. Enforces package
membership, path safety, and a size ceiling. Never exposes storage credentials
or bucket URLs: bytes are proxied by central.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.media_encoding import MediaPackage
from app.services.object_storage.origin_read import (
    fetch_package_object_bytes,
    origin_hls_read_fallback_enabled,
    package_allows_origin_read,
)
from app.services.streaming.paths import (
    StreamPathError,
    resolve_master_playlist,
    resolve_segment,
    resolve_variant_playlist,
)

_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_LOCAL_MISS = frozenset({"package_missing", "not_found"})


class CDNOriginError(Exception):
    def __init__(self, code: str, status_code: int = 404) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class OriginObjectBytes:
    data: bytes
    content_type: str
    sha256: str
    source: str  # local | origin


def _content_type(relative_path: str) -> str:
    lower = relative_path.lower()
    if lower.endswith(".m3u8"):
        return "application/vnd.apple.mpegurl"
    if lower.endswith(".vtt"):
        return "text/vtt"
    return "video/mp2t"


def _split(relative_path: str) -> tuple[str | None, str]:
    rel = (relative_path or "").replace("\\", "/").strip().strip("/")
    parts = rel.split("/")
    if len(parts) == 1:
        return None, parts[0]
    if len(parts) == 2:
        return parts[0], parts[1]
    raise CDNOriginError("path_rejected", 400)


def read_package_object(
    db: Session,
    *,
    asset_id: str,
    package_id: str,
    relative_path: str,
    settings: Settings | None = None,
) -> OriginObjectBytes:
    cfg = settings or get_settings()
    if not _ID_RE.fullmatch(asset_id or "") or not _ID_RE.fullmatch(package_id or ""):
        raise CDNOriginError("invalid_identifier", 400)
    if ".." in relative_path or "%" in relative_path or "\\" in relative_path:
        raise CDNOriginError("path_rejected", 400)
    package = db.get(MediaPackage, package_id)
    if package is None or package.media_asset_id != asset_id:
        raise CDNOriginError("package_not_found", 404)
    if package.status != "completed" or not package.is_active:
        raise CDNOriginError("package_not_active", 404)

    label, name = _split(relative_path)
    try:
        if label is None:
            if name != "master.m3u8":
                raise CDNOriginError("path_rejected", 400)
            path = resolve_master_playlist(package)
        elif name == "index.m3u8":
            path = resolve_variant_playlist(package, label)
        else:
            path = resolve_segment(package, label, name)
        data = path.read_bytes()
        source = "local"
    except StreamPathError as exc:
        if exc.code in {"traversal_rejected", "escape_rejected", "symlink_rejected", "outside_packages"}:
            raise CDNOriginError("path_rejected", 400) from exc
        if exc.code in {"invalid_label", "invalid_segment", "unsupported_extension"}:
            raise CDNOriginError("path_rejected", 400) from exc
        if (
            exc.code in _LOCAL_MISS
            and origin_hls_read_fallback_enabled(cfg)
            and package_allows_origin_read(package)
        ):
            logical = name if label is None else f"{label}/{name}"
            try:
                data = fetch_package_object_bytes(package, logical, settings=cfg)
            except StreamPathError as inner:
                raise CDNOriginError("not_found", 404) from inner
            source = "origin"
        else:
            raise CDNOriginError("not_found", 404) from exc
    if len(data) > int(cfg.cdn_origin_max_object_bytes):
        raise CDNOriginError("object_too_large", 413)
    return OriginObjectBytes(
        data=data,
        content_type=_content_type(name),
        sha256=hashlib.sha256(data).hexdigest(),
        source=source,
    )
