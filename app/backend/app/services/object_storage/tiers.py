"""Storage roles and provider kinds for the hybrid CDN foundation."""

from __future__ import annotations

from enum import StrEnum


class StorageRole(StrEnum):
    """Logical role of a storage backend in the hybrid architecture."""

    # Disposable encode/upload scratch and current production media root.
    LOCAL_WORKSPACE = "local_workspace"
    # Durable source of truth for masters + HLS packages (MinIO/Ceph/S3 API).
    CENTRAL_ORIGIN = "central_origin"
    # Optional policy-driven hot tier (e.g. Cloudflare R2) — never the full library.
    HOT_CDN = "hot_cdn"
    # Future pull-through caches on branch servers (Phase 2+).
    BRANCH_CACHE = "branch_cache"


class StorageProviderKind(StrEnum):
    """Concrete provider implementations."""

    LOCAL = "local"
    S3_COMPATIBLE = "s3_compatible"
    # R2 uses the S3-compatible client with a separate role/config block.
    R2 = "r2"
