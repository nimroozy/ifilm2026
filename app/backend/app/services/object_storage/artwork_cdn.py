"""Publish catalog artwork (and optional trailer binaries) to Cloudflare R2 CDN.

Movies / HLS packages stay on local MEDIA_ROOT. This module only handles the
public website media tree under ARTWORK_ROOT (posters, backdrops, logos, stills)
and optional trailer binaries under MEDIA_ROOT/trailers.

## Enablement precedence

1. **Host kill switch** ``ENABLE_ARTWORK_CDN_SYNC`` must be true.
2. When an Admin IntegrationConfig storage row exists:
   ``config_json.artwork_cdn_enabled`` is authoritative beneath the host switch.
   ``row.enabled`` (private/hot-tier) does **not** enable artwork publishing.
3. When **no** IntegrationConfig row exists (legacy env-only):
   host switch + env ``R2_*`` + env ``ARTWORK_CDN_PUBLIC_BASE_URL`` may enable
   the publish path.

Failures never delete local files; callers fall back to /artwork/... URLs.
"""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.services.object_storage.factory import get_artwork_cdn_storage
from app.services.object_storage.keys import ObjectKeyBuilder
from app.services.object_storage.protocol import ObjectStorage

logger = logging.getLogger(__name__)

ArtworkPublishingStatus = Literal["active", "disabled", "blocked_by_server_capability"]

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


@dataclass(frozen=True)
class ArtworkCdnEffectiveState:
    """Secret-free runtime decision for artwork CDN publishing."""

    host_capability: bool
    admin_requested: bool
    has_admin_row: bool
    credentials_configured: bool
    public_base_configured: bool
    storage_config_valid: bool
    effective: bool
    publishing_status: ArtworkPublishingStatus


class ArtworkCdnError(RuntimeError):
    """Raised for configuration / publish failures (never includes secrets)."""


def artwork_cdn_sync_enabled(settings: Settings | None = None) -> bool:
    """Host kill switch only (ENABLE_ARTWORK_CDN_SYNC)."""
    cfg = settings or get_settings()
    return bool(cfg.enable_artwork_cdn_sync)


def _env_r2_complete(cfg: Settings) -> bool:
    return all(
        (
            str(cfg.r2_endpoint_url or "").strip(),
            str(cfg.r2_bucket or "").strip(),
            str(cfg.r2_access_key_id or "").strip(),
            str(cfg.r2_secret_access_key or "").strip(),
        )
    )


def resolve_artwork_cdn_public_base_url(
    settings: Settings | None = None,
    *,
    db: Session | None = None,
) -> str:
    """Return the public CDN base URL (no trailing slash), or empty when unset.

    Env ``ARTWORK_CDN_PUBLIC_BASE_URL`` wins when set; otherwise admin
    ``public_base_url`` is used when a storage row exists.
    """
    cfg = settings or get_settings()
    base = (cfg.artwork_cdn_public_base_url or "").strip().rstrip("/")
    if base:
        return base
    if db is not None:
        from app.services.cdn_management import storage_row

        row = storage_row(db)
        if row is not None:
            return str((row.config_json or {}).get("public_base_url") or "").strip().rstrip("/")
    return ""


def evaluate_artwork_cdn_effective(
    settings: Settings | None = None,
    *,
    db: Session | None = None,
) -> ArtworkCdnEffectiveState:
    """Shared runtime decision: host ∩ admin ∩ credentials ∩ public base ∩ config."""
    cfg = settings or get_settings()
    host = bool(cfg.enable_artwork_cdn_sync)

    row = None
    if db is not None:
        from app.services.cdn_management import storage_row

        row = storage_row(db)

    if row is not None:
        data = dict(row.config_json or {})
        admin_requested = bool(data.get("artwork_cdn_enabled"))
        credentials_ok = bool(row.secret_ciphertext)
        endpoint = str(data.get("endpoint_url") or "").strip()
        bucket = str(data.get("bucket") or "").strip()
        storage_ok = bool(endpoint and bucket and credentials_ok)
        public_base = resolve_artwork_cdn_public_base_url(cfg, db=db)
        public_ok = bool(public_base)
        # row.enabled (hot-tier) must NOT substitute for artwork_cdn_enabled.
        effective = bool(host and admin_requested and credentials_ok and public_ok and storage_ok)
        has_admin_row = True
    else:
        # Legacy env-only path when no Admin IntegrationConfig row exists.
        admin_requested = False
        credentials_ok = _env_r2_complete(cfg)
        public_base = (cfg.artwork_cdn_public_base_url or "").strip().rstrip("/")
        public_ok = bool(public_base)
        storage_ok = credentials_ok
        effective = bool(host and credentials_ok and public_ok and storage_ok)
        has_admin_row = False

    if admin_requested and not host:
        status: ArtworkPublishingStatus = "blocked_by_server_capability"
    elif effective:
        status = "active"
    else:
        status = "disabled"

    return ArtworkCdnEffectiveState(
        host_capability=host,
        admin_requested=admin_requested,
        has_admin_row=has_admin_row,
        credentials_configured=credentials_ok,
        public_base_configured=public_ok,
        storage_config_valid=storage_ok,
        effective=effective,
        publishing_status=status,
    )


def artwork_cdn_ready(
    settings: Settings | None = None,
    *,
    db: Session | None = None,
) -> bool:
    """True when effective artwork publishing is fully enabled."""
    return evaluate_artwork_cdn_effective(settings, db=db).effective


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


def _object_key_prefix(cfg: Settings, db: Session | None) -> str:
    prefix = (cfg.media_object_key_prefix or "ifilm").strip() or "ifilm"
    if db is not None:
        from app.services.cdn_management import storage_row

        row = storage_row(db)
        if row is not None:
            admin_prefix = str((row.config_json or {}).get("object_key_prefix") or "").strip()
            if admin_prefix:
                prefix = admin_prefix
    return prefix


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
    state = evaluate_artwork_cdn_effective(cfg, db=db)
    if not state.effective:
        return None

    base = resolve_artwork_cdn_public_base_url(cfg, db=db)
    if not base:
        raise ArtworkCdnError("ARTWORK_CDN_PUBLIC_BASE_URL (or admin public_base_url) is required")

    store = storage or get_artwork_cdn_storage(cfg, db=db)
    if store is None:
        raise ArtworkCdnError("R2 credentials are not configured for artwork CDN")

    if not source.is_file():
        raise ArtworkCdnError("Artwork source file is missing")

    keys = ObjectKeyBuilder(prefix=_object_key_prefix(cfg, db))
    # Filenames under ARTWORK_ROOT are content-addressed (hash segment) so
    # replacements mint a new object key and avoid stale CDN caches.
    object_key = keys.artwork_relative_key(relative_path=relative_path)
    skipped = False
    if skip_if_exists and store.exists(key=object_key):
        skipped = True
    else:
        store.put_file(key=object_key, source=source, content_type=_guess_content_type(source))
        # Verify the object is readable before returning a public CDN URL.
        if not store.exists(key=object_key):
            raise ArtworkCdnError("Artwork CDN upload could not be verified")
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
    state = evaluate_artwork_cdn_effective(cfg, db=db)
    if not state.effective:
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

    keys = ObjectKeyBuilder(prefix=_object_key_prefix(cfg, db))
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
