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

    # Phase 3 control-plane flag dependencies (independent of object storage).
    if settings.enable_edge_grant_issue and not settings.enable_branch_cache_control_plane:
        errors.append("ENABLE_EDGE_GRANT_ISSUE requires ENABLE_BRANCH_CACHE_CONTROL_PLANE=true")
    if (
        settings.enable_branch_cache_shadow_routing
        and not settings.enable_branch_cache_control_plane
    ):
        errors.append(
            "ENABLE_BRANCH_CACHE_SHADOW_ROUTING requires ENABLE_BRANCH_CACHE_CONTROL_PLANE=true"
        )
    if settings.enable_edge_grant_issue:
        if not (settings.edge_grant_private_key_pem or "").strip():
            errors.append(
                "EDGE_GRANT_PRIVATE_KEY_PEM is required when ENABLE_EDGE_GRANT_ISSUE=true"
            )
        if not (settings.edge_grant_public_key_pem or "").strip():
            errors.append("EDGE_GRANT_PUBLIC_KEY_PEM is required when ENABLE_EDGE_GRANT_ISSUE=true")
        ttl = int(settings.edge_grant_ttl_seconds or 0)
        if ttl < 15 or ttl > 300:
            errors.append("EDGE_GRANT_TTL_SECONDS must be between 15 and 300")
    if is_prod_like(settings.app_env) and settings.enable_branch_cache_control_plane:
        if settings.enable_cdn_sync:
            errors.append(
                "ENABLE_CDN_SYNC must remain false when branch-cache control plane is used"
            )

    # Phase 4 data-plane simulation flags (offline only).
    if settings.enable_branch_cache_pull_through and not settings.enable_branch_cache_data_plane_sim:
        errors.append(
            "ENABLE_BRANCH_CACHE_PULL_THROUGH requires ENABLE_BRANCH_CACHE_DATA_PLANE_SIM=true"
        )
    if settings.enable_branch_cache_local_serve and not settings.enable_branch_cache_data_plane_sim:
        errors.append(
            "ENABLE_BRANCH_CACHE_LOCAL_SERVE requires ENABLE_BRANCH_CACHE_DATA_PLANE_SIM=true"
        )
    if settings.enable_branch_cache_data_plane_sim:
        if not (settings.edge_grant_public_key_pem or "").strip():
            errors.append(
                "EDGE_GRANT_PUBLIC_KEY_PEM is required when ENABLE_BRANCH_CACHE_DATA_PLANE_SIM=true"
            )
        if is_prod_like(settings.app_env):
            errors.append(
                "ENABLE_BRANCH_CACHE_DATA_PLANE_SIM must remain false in staging/production "
                "(Phase 4 is offline simulation only; no live branch data-plane)"
            )
        if settings.enable_cdn_sync:
            errors.append(
                "ENABLE_CDN_SYNC must remain false when branch-cache data-plane sim is used"
            )

    # Phase 5 pilot lab tooling (offline only).
    if settings.enable_branch_cache_pilot_lab and is_prod_like(settings.app_env):
        errors.append(
            "ENABLE_BRANCH_CACHE_PILOT_LAB must remain false in staging/production "
            "(Phase 5 is offline capacity/SLO lab tooling only)"
        )
    if settings.enable_branch_cache_pilot_lab and settings.enable_cdn_sync:
        errors.append(
            "ENABLE_CDN_SYNC must remain false when branch-cache pilot lab is used"
        )

    # Phase 6 isolated HTTP service candidate (offline / lab only).
    if settings.enable_branch_cache_http_service and is_prod_like(settings.app_env):
        errors.append(
            "ENABLE_BRANCH_CACHE_HTTP_SERVICE must remain false in staging/production "
            "(Phase 6 is an offline ASGI candidate; no production container)"
        )
    if settings.enable_branch_cache_http_service and settings.enable_cdn_sync:
        errors.append(
            "ENABLE_CDN_SYNC must remain false when branch-cache HTTP service is used"
        )
    if settings.enable_branch_cache_http_lab_https_adapter and not (
        settings.enable_branch_cache_http_service
    ):
        errors.append(
            "ENABLE_BRANCH_CACHE_HTTP_LAB_HTTPS_ADAPTER requires "
            "ENABLE_BRANCH_CACHE_HTTP_SERVICE=true"
        )
    if settings.enable_branch_cache_http_lab_https_adapter and is_prod_like(settings.app_env):
        errors.append(
            "ENABLE_BRANCH_CACHE_HTTP_LAB_HTTPS_ADAPTER must remain false in staging/production"
        )
    if settings.enable_branch_cache_http_lab_artifact and is_prod_like(settings.app_env):
        errors.append(
            "ENABLE_BRANCH_CACHE_HTTP_LAB_ARTIFACT must remain false in staging/production "
            "(Phase 7 lab/CI container artifact only)"
        )
    if settings.enable_branch_cache_http_lab_artifact and not (
        settings.enable_branch_cache_http_service
    ):
        errors.append(
            "ENABLE_BRANCH_CACHE_HTTP_LAB_ARTIFACT requires ENABLE_BRANCH_CACHE_HTTP_SERVICE=true"
        )

    # Phase 8 mTLS staging-candidate (offline/loopback package; not live activation).
    if settings.enable_branch_cache_http_mtls_staging_candidate and is_prod_like(
        settings.app_env
    ):
        errors.append(
            "ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE must remain false in "
            "staging/production until a separate explicit deployment step"
        )
    if settings.enable_branch_cache_http_mtls_staging_candidate and not (
        settings.enable_branch_cache_http_service
    ):
        errors.append(
            "ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE requires "
            "ENABLE_BRANCH_CACHE_HTTP_SERVICE=true"
        )
    if settings.enable_branch_cache_http_mtls_staging_candidate and settings.enable_cdn_sync:
        errors.append(
            "ENABLE_CDN_SYNC must remain false when mTLS staging-candidate is used"
        )

    # Phase 9 one-node staging deploy apply gate (plan/render is offline; apply stays off).
    if settings.enable_branch_cache_one_node_staging_deploy and is_prod_like(settings.app_env):
        errors.append(
            "ENABLE_BRANCH_CACHE_ONE_NODE_STAGING_DEPLOY must remain false in "
            "staging/production; Phase 9 is plan/render only"
        )
    if settings.enable_branch_cache_one_node_staging_deploy:
        errors.append(
            "ENABLE_BRANCH_CACHE_ONE_NODE_STAGING_DEPLOY must remain false until a "
            "separately reviewed remote-apply mechanism exists"
        )

    # Artwork CDN (R2 public images/trailers) — independent of MinIO/AWS origin.
    if settings.enable_artwork_cdn_sync:
        base = (settings.artwork_cdn_public_base_url or "").strip()
        if base:
            parsed_base = urlparse(base)
            if parsed_base.scheme != "https" or not parsed_base.hostname:
                errors.append("ARTWORK_CDN_PUBLIC_BASE_URL must be an absolute https URL")
        r2_fields = [
            (settings.r2_endpoint_url or "").strip(),
            (settings.r2_bucket or "").strip(),
            (settings.r2_access_key_id or "").strip(),
            (settings.r2_secret_access_key or "").strip(),
        ]
        present = [bool(v) for v in r2_fields]
        if any(present) and not all(present):
            errors.append(
                "R2_ENDPOINT_URL, R2_BUCKET, R2_ACCESS_KEY_ID, and R2_SECRET_ACCESS_KEY "
                "must all be set together for artwork CDN"
            )
        if all(present):
            parsed = urlparse(r2_fields[0])
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                errors.append("R2_ENDPOINT_URL must be an absolute http(s) URL")
            if not base:
                errors.append(
                    "ARTWORK_CDN_PUBLIC_BASE_URL is required when ENABLE_ARTWORK_CDN_SYNC=true "
                    "with env R2 credentials"
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
