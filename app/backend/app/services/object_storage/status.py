"""Secret-free storage status for ops / diagnostics."""

from __future__ import annotations

from urllib.parse import urlparse

from app.core.config import Settings, get_settings


def _endpoint_host(url: str) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    host = urlparse(raw).hostname
    return host


def safe_storage_status(settings: Settings | None = None) -> dict:
    """Return configured storage roles without credentials or secrets.

    Safe for logs, admin diagnostics, and documentation snapshots.
    """
    cfg = settings or get_settings()
    origin_provider = (cfg.media_origin_provider or "local").strip().lower()
    return {
        "enable_object_storage": bool(cfg.enable_object_storage),
        "enable_r2_hot_tier": bool(cfg.enable_r2_hot_tier),
        "enable_cdn_sync_legacy": bool(cfg.enable_cdn_sync),
        "roles": {
            "local_workspace": {
                "provider": "local",
                "media_root_configured": bool(cfg.media_root),
            },
            "central_origin": {
                "provider": origin_provider if cfg.enable_object_storage else "local",
                "endpoint_host": _endpoint_host(cfg.media_origin_endpoint_url)
                if cfg.enable_object_storage and origin_provider == "s3_compatible"
                else None,
                "bucket_configured": bool((cfg.media_origin_bucket or "").strip())
                if cfg.enable_object_storage
                else False,
                "prefix": (cfg.media_object_key_prefix or "ifilm").strip() or "ifilm",
                "force_path_style": bool(cfg.media_origin_force_path_style),
            },
            "hot_cdn": {
                "enabled": bool(cfg.enable_object_storage and cfg.enable_r2_hot_tier),
                "provider": "r2" if cfg.enable_r2_hot_tier else None,
                "endpoint_host": _endpoint_host(cfg.r2_endpoint_url)
                if cfg.enable_r2_hot_tier
                else None,
                "bucket_configured": bool((cfg.r2_bucket or "").strip())
                if cfg.enable_r2_hot_tier
                else False,
                "max_titles": int(cfg.cdn_hot_tier_max_titles),
                "cooldown_days": int(cfg.cdn_hot_tier_cooldown_days),
                "promote_views_threshold": int(cfg.cdn_hot_tier_promote_views_threshold),
            },
            "branch_cache": {
                "implemented": False,
                "note": "Phase 2+: pull-through caches with verification-only public keys",
            },
        },
        "policy": {
            "mirror_full_library_to_r2": False,
            "cloudflare_stream_default_delivery": False,
            "permanent_public_movie_urls": False,
            "playback_remains_session_authorized": True,
        },
    }
