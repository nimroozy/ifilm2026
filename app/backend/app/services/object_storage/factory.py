"""Factory helpers for storage roles (feature-flag gated)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, get_settings
from app.services.object_storage.local import LocalFilesystemStorage
from app.services.object_storage.protocol import ObjectStorage
from app.services.object_storage.s3_compatible import S3CompatibleConfig, S3CompatibleStorage
from app.services.object_storage.tiers import StorageProviderKind, StorageRole


class ObjectStorageNotEnabledError(RuntimeError):
    """Raised when a remote storage role is requested while flags are off."""


def get_local_workspace_storage(settings: Settings | None = None) -> ObjectStorage:
    """Always available: encode/upload workspace under MEDIA_ROOT."""
    cfg = settings or get_settings()
    return LocalFilesystemStorage(
        root=Path(cfg.media_root),
        role=StorageRole.LOCAL_WORKSPACE,
    )


def get_central_origin_storage(settings: Settings | None = None) -> ObjectStorage:
    """Durable central origin. Defaults to local until object storage is enabled."""
    cfg = settings or get_settings()
    if not cfg.enable_object_storage:
        return get_local_workspace_storage(cfg)

    provider = (cfg.media_origin_provider or "local").strip().lower()
    if provider == StorageProviderKind.LOCAL.value:
        return LocalFilesystemStorage(
            root=Path(cfg.media_root),
            role=StorageRole.CENTRAL_ORIGIN,
        )
    if provider == StorageProviderKind.S3_COMPATIBLE.value:
        return S3CompatibleStorage(
            S3CompatibleConfig(
                endpoint_url=cfg.media_origin_endpoint_url,
                bucket=cfg.media_origin_bucket,
                region=cfg.media_origin_region,
                access_key_id=cfg.media_origin_access_key_id,
                secret_access_key=cfg.media_origin_secret_access_key,
                force_path_style=cfg.media_origin_force_path_style,
                provider_kind=StorageProviderKind.S3_COMPATIBLE,
                role=StorageRole.CENTRAL_ORIGIN,
            )
        )
    raise ValueError(f"Unsupported MEDIA_ORIGIN_PROVIDER: {provider}")


def get_hot_tier_storage(settings: Settings | None = None) -> ObjectStorage | None:
    """Optional R2/hot CDN tier. Returns None when disabled (default)."""
    cfg = settings or get_settings()
    if not cfg.enable_object_storage or not cfg.enable_r2_hot_tier:
        return None
    return S3CompatibleStorage(
        S3CompatibleConfig(
            endpoint_url=cfg.r2_endpoint_url,
            bucket=cfg.r2_bucket,
            region=cfg.r2_region or "auto",
            access_key_id=cfg.r2_access_key_id,
            secret_access_key=cfg.r2_secret_access_key,
            force_path_style=False,
            provider_kind=StorageProviderKind.R2,
            role=StorageRole.HOT_CDN,
        )
    )
