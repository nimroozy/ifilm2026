"""Publish catalog artwork (and optional trailer binaries) to Cloudflare R2 CDN.

Movies / HLS packages stay on local MEDIA_ROOT. This module only handles the
public website media tree under ARTWORK_ROOT (posters, backdrops, logos, stills)
and optional trailer binaries under MEDIA_ROOT/trailers.

Activation requires:
  ENABLE_ARTWORK_CDN_SYNC=true
  ARTWORK_CDN_PUBLIC_BASE_URL=https://cdn.example.com  (or admin R2 public_base_url)
  R2 credentials (env R2_* or admin-encrypted IntegrationConfig)

Failures never delete local files; callers fall back to /artwork/... URLs.
"""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.services.object_storage.factory import get_artwork_cdn_storage
from app.services.object_storage.keys import ObjectKeyBuilder
from app.services.object_storage.protocol import ObjectStorage

logger = logging.getLogger(__name__)

_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}


@dataclass(frozen=True)
class ArtworkCdnPublishResult:
    object_key: str
    public_url: str
    skipped_existing: bool


class ArtworkCdnError(RuntimeError):
    """Raised for configuration / publish failures (never includes secrets)."""


def artwork_cdn_sync_enabled(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return bool(cfg.enable_artwork_cdn_sync)


def resolve_artwork_cdn_public_base_url(
    settings: Settings | None = None,
    *,
    db: Session | None = None,
) -> str:
    """Return the public CDN base URL (no trailing slash), or empty when unset."""
    cfg = settings or get_settings()
    base = (cfg.artwork_cdn_public_base_url or "").strip().rstrip("/")
    if base:
        return base
    if db is not None:
        from app.services.cdn_management import get_r2

        data = get_r2(db)
        return str(data.get("public_base_url") or "").strip().rstrip("/")
    return ""


def artwork_cdn_ready(
    settings: Settings | None = None,
    *,
    db: Session | None = None,
) -> bool:
    """True when sync is enabled and a public base URL + R2 storage are available."""
    cfg = settings or get_settings()
    if not artwork_cdn_sync_enabled(cfg):
        return False
    if not resolve_artwork_cdn_public_base_url(cfg, db=db):
        return False
    return get_artwork_cdn_storage(cfg, db=db) is not None


def public_cdn_url(*, base_url: str, object_key: str) -> str:
    base = base_url.strip().rstrip("/")
    key = object_key.strip().lstrip("/")
    if not base or not key:
        raise ArtworkCdnError("CDN base URL and object key are required")
    return f"{base}/{key}"


def _guess_content_type(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in _CONTENT_TYPES:
        return _CONTENT_TYPES[ext]
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed


def publish_artwork_file(
    *,
    relative_path: str,
    source: Path,
    settings: Settings | None = None,
    db: Session | None = None,
    storage: ObjectStorage | None = None,
    skip_if_exists: bool = True,
) -> ArtworkCdnPublishResult | None:
    """Upload one ARTWORK_ROOT-relative file to R2 and return its public CDN URL.

    Returns None when artwork CDN is disabled / not configured (caller keeps local URL).
    """
    cfg = settings or get_settings()
    if not artwork_cdn_sync_enabled(cfg):
        return None

    base = resolve_artwork_cdn_public_base_url(cfg, db=db)
    if not base:
        raise ArtworkCdnError("ARTWORK_CDN_PUBLIC_BASE_URL (or admin public_base_url) is required")

    store = storage or get_artwork_cdn_storage(cfg, db=db)
    if store is None:
        raise ArtworkCdnError("R2 credentials are not configured for artwork CDN")

    if not source.is_file():
        raise ArtworkCdnError("Artwork source file is missing")

    keys = ObjectKeyBuilder(prefix=(cfg.media_object_key_prefix or "ifilm").strip() or "ifilm")
    object_key = keys.artwork_relative_key(relative_path=relative_path)
    skipped = False
    if skip_if_exists and store.exists(key=object_key):
        skipped = True
    else:
        store.put_file(key=object_key, source=source, content_type=_guess_content_type(source))
    return ArtworkCdnPublishResult(
        object_key=object_key,
        public_url=public_cdn_url(base_url=base, object_key=object_key),
        skipped_existing=skipped,
    )


def try_publish_artwork_file(
    *,
    relative_path: str,
    source: Path,
    settings: Settings | None = None,
    db: Session | None = None,
) -> str | None:
    """Best-effort publish; logs and returns None on failure so local URLs remain valid."""
    try:
        result = publish_artwork_file(
            relative_path=relative_path,
            source=source,
            settings=settings,
            db=db,
        )
        return result.public_url if result else None
    except Exception as exc:  # noqa: BLE001 — never break local artwork writes
        logger.warning(
            "artwork_cdn_publish_failed relative_path=%s error=%s",
            relative_path,
            type(exc).__name__,
        )
        return None


def publish_trailer_binary(
    *,
    asset_id: str,
    stored_filename: str,
    source: Path,
    settings: Settings | None = None,
    db: Session | None = None,
    storage: ObjectStorage | None = None,
) -> ArtworkCdnPublishResult | None:
    """Upload a trailer binary from MEDIA_ROOT/trailers to the public artwork CDN bucket.

    HLS movie packages must never use this path.
    """
    cfg = settings or get_settings()
    if not artwork_cdn_sync_enabled(cfg):
        return None
    base = resolve_artwork_cdn_public_base_url(cfg, db=db)
    if not base:
        raise ArtworkCdnError("ARTWORK_CDN_PUBLIC_BASE_URL (or admin public_base_url) is required")
    store = storage or get_artwork_cdn_storage(cfg, db=db)
    if store is None:
        raise ArtworkCdnError("R2 credentials are not configured for artwork CDN")
    if not source.is_file():
        raise ArtworkCdnError("Trailer source file is missing")

    from app.services.object_storage.keys import StorageObjectKind

    keys = ObjectKeyBuilder(prefix=(cfg.media_object_key_prefix or "ifilm").strip() or "ifilm")
    object_key = keys.artwork_key(
        kind=StorageObjectKind.TRAILER,
        asset_id=asset_id,
        stored_filename=stored_filename,
    )
    store.put_file(key=object_key, source=source, content_type=_guess_content_type(source))
    return ArtworkCdnPublishResult(
        object_key=object_key,
        public_url=public_cdn_url(base_url=base, object_key=object_key),
        skipped_existing=False,
    )
