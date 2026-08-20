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
        "enable_origin_package_sync": bool(cfg.enable_origin_package_sync),
        "enable_origin_hls_read_fallback": bool(cfg.enable_origin_hls_read_fallback),
        "enable_branch_cache_control_plane": bool(cfg.enable_branch_cache_control_plane),
        "enable_edge_grant_issue": bool(cfg.enable_edge_grant_issue),
        "enable_branch_cache_shadow_routing": bool(cfg.enable_branch_cache_shadow_routing),
        "enable_branch_cache_data_plane_sim": bool(cfg.enable_branch_cache_data_plane_sim),
        "enable_branch_cache_pull_through": bool(cfg.enable_branch_cache_pull_through),
        "enable_branch_cache_local_serve": bool(cfg.enable_branch_cache_local_serve),
        "enable_branch_cache_pilot_lab": bool(cfg.enable_branch_cache_pilot_lab),
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
                "control_plane": bool(cfg.enable_branch_cache_control_plane),
                "data_plane_sim": bool(cfg.enable_branch_cache_data_plane_sim),
                "data_plane_active": bool(cfg.enable_branch_cache_data_plane_sim),
                "client_redirect_active": False,
                "shadow_routing": bool(cfg.enable_branch_cache_shadow_routing),
                "edge_grant_issue": bool(cfg.enable_edge_grant_issue),
                "pull_through": bool(cfg.enable_branch_cache_pull_through),
                "local_serve": bool(cfg.enable_branch_cache_local_serve),
                "pilot_lab": bool(cfg.enable_branch_cache_pilot_lab),
                "live_http_origin": False,
                "note": (
                    "Phase 5: offline capacity/SLO/pilot-gate lab tooling; "
                    "no live branch delivery or client redirects"
                ),
            },
        },
        "policy": {
            "mirror_full_library_to_r2": False,
            "cloudflare_stream_default_delivery": False,
            "permanent_public_movie_urls": False,
            "playback_remains_session_authorized": True,
            "branch_cache_default_off": True,
            "branch_data_plane_sim_only": True,
            "live_pilot_requires_human_and_staging": True,
        },
    }
