"""Startup validation for object-storage / hybrid CDN Phase 1 settings."""

from __future__ import annotations

from urllib.parse import urlparse

from app.core.config import Settings
from app.core.runtime import is_prod_like


def collect_object_storage_errors(settings: Settings) -> list[str]:
    """Validate object-storage configuration. Never echo secret values."""
    errors: list[str] = []

    # Legacy experimental edge sync must stay off in staging/production.
    if is_prod_like(settings.app_env) and settings.enable_cdn_sync:
        errors.append(
            "ENABLE_CDN_SYNC must remain false in staging/production "
            "(experimental edge sync is not a signed branch-cache protocol)"
        )

    if not settings.enable_object_storage:
        if settings.enable_r2_hot_tier:
            errors.append("ENABLE_R2_HOT_TIER requires ENABLE_OBJECT_STORAGE=true")
        if settings.enable_origin_package_sync:
            errors.append("ENABLE_ORIGIN_PACKAGE_SYNC requires ENABLE_OBJECT_STORAGE=true")
        if settings.enable_origin_hls_read_fallback:
            errors.append("ENABLE_ORIGIN_HLS_READ_FALLBACK requires ENABLE_OBJECT_STORAGE=true")
        return errors

    provider = (settings.media_origin_provider or "local").strip().lower()
    if provider not in {"local", "s3_compatible"}:
        errors.append("MEDIA_ORIGIN_PROVIDER must be local or s3_compatible")

    if provider == "s3_compatible":
        if not (settings.media_origin_endpoint_url or "").strip():
            errors.append("MEDIA_ORIGIN_ENDPOINT_URL is required for s3_compatible origin")
        else:
            parsed = urlparse(settings.media_origin_endpoint_url.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                errors.append("MEDIA_ORIGIN_ENDPOINT_URL must be an absolute http(s) URL")
        if not (settings.media_origin_bucket or "").strip():
            errors.append("MEDIA_ORIGIN_BUCKET is required for s3_compatible origin")
        if not (settings.media_origin_access_key_id or "").strip():
            errors.append("MEDIA_ORIGIN_ACCESS_KEY_ID is required for s3_compatible origin")
        if not (settings.media_origin_secret_access_key or "").strip():
            errors.append("MEDIA_ORIGIN_SECRET_ACCESS_KEY is required for s3_compatible origin")

    if settings.enable_r2_hot_tier:
        if int(settings.cdn_hot_tier_max_titles) <= 0:
            errors.append(
                "CDN_HOT_TIER_MAX_TITLES must be > 0 when ENABLE_R2_HOT_TIER=true "
                "(R2 must not mirror the full library by default)"
            )
        if not (settings.r2_endpoint_url or "").strip():
            errors.append("R2_ENDPOINT_URL is required when ENABLE_R2_HOT_TIER=true")
        else:
            parsed = urlparse(settings.r2_endpoint_url.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                errors.append("R2_ENDPOINT_URL must be an absolute http(s) URL")
        if not (settings.r2_bucket or "").strip():
            errors.append("R2_BUCKET is required when ENABLE_R2_HOT_TIER=true")
        if not (settings.r2_access_key_id or "").strip():
            errors.append("R2_ACCESS_KEY_ID is required when ENABLE_R2_HOT_TIER=true")
        if not (settings.r2_secret_access_key or "").strip():
            errors.append("R2_SECRET_ACCESS_KEY is required when ENABLE_R2_HOT_TIER=true")

    # Staging/production: object storage may be configured for readiness, but
    # incomplete remote origin config is rejected when the flag is on.
    if is_prod_like(settings.app_env) and provider == "local" and settings.enable_object_storage:
        # Allowed: flag on with local provider for staged cutover drills.
        pass

    return errors
