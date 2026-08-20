"""Lab/CI ASGI entry for the isolated branch-cache HTTP service.

Used only by ``Dockerfile.branch-cache.lab`` / validate-only harness.
Not mounted in the central app. Requires explicit lab artifact flag.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from app.core.config import Settings
from app.services.branch_cache.data_plane.origin import LocalDirOriginFetcher
from app.services.branch_cache.service.app import create_branch_cache_app
from app.services.branch_cache.service.config import (
    BranchServiceConfig,
    BranchServiceConfigError,
    _is_prod_like,
)


def _truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _forbid_env_secrets() -> None:
    """Reject credential-bearing env that must never ship on a branch node."""
    forbidden_present = []
    checks = [
        ("EDGE_GRANT_PRIVATE_KEY_PEM", os.environ.get("EDGE_GRANT_PRIVATE_KEY_PEM")),
        ("DATABASE_URL", os.environ.get("DATABASE_URL")),
        ("REDIS_URL", os.environ.get("REDIS_URL")),
        ("POSTGRES_PASSWORD", os.environ.get("POSTGRES_PASSWORD")),
        ("REDIS_PASSWORD", os.environ.get("REDIS_PASSWORD")),
        ("JWT_SECRET", os.environ.get("JWT_SECRET")),
        ("PLAYBACK_TOKEN_SECRET", os.environ.get("PLAYBACK_TOKEN_SECRET")),
        ("ADMIN_BOOTSTRAP_PASSWORD", os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")),
        ("RADIUS_SECRET", os.environ.get("RADIUS_SECRET")),
        ("AWS_SECRET_ACCESS_KEY", os.environ.get("AWS_SECRET_ACCESS_KEY")),
        ("AWS_ACCESS_KEY_ID", os.environ.get("AWS_ACCESS_KEY_ID")),
        ("R2_SECRET_ACCESS_KEY", os.environ.get("R2_SECRET_ACCESS_KEY")),
        ("MEDIA_ORIGIN_SECRET_ACCESS_KEY", os.environ.get("MEDIA_ORIGIN_SECRET_ACCESS_KEY")),
        ("PORTAL_CLIENT_SECRET", os.environ.get("PORTAL_CLIENT_SECRET")),
        ("SAS_CLIENT_SECRET", os.environ.get("SAS_CLIENT_SECRET")),
    ]
    for key, val in checks:
        if val and str(val).strip():
            forbidden_present.append(key)
    if forbidden_present:
        raise BranchServiceConfigError(
            "branch lab artifact forbids credential env: " + ",".join(forbidden_present),
            code="secrets_forbidden",
        )


def load_lab_settings() -> Settings:
    """Build Settings for the lab artifact without loading a .env secrets file."""
    app_env = (os.environ.get("APP_ENV") or "development").strip().lower()
    if _is_prod_like(app_env):
        raise BranchServiceConfigError(
            "branch lab artifact cannot start in staging/production",
            code="prod_forbidden",
        )
    if not _truthy("ENABLE_BRANCH_CACHE_HTTP_LAB_ARTIFACT"):
        raise BranchServiceConfigError(
            "ENABLE_BRANCH_CACHE_HTTP_LAB_ARTIFACT must be true for this entrypoint",
            code="lab_artifact_flag",
        )
    if not _truthy("ENABLE_BRANCH_CACHE_HTTP_SERVICE"):
        raise BranchServiceConfigError(
            "ENABLE_BRANCH_CACHE_HTTP_SERVICE must be true for this entrypoint",
            code="flag_off",
        )
    _forbid_env_secrets()

    pub = (os.environ.get("EDGE_GRANT_PUBLIC_KEY_PEM") or "").strip()
    if not pub:
        # Allow file path form for lab mounts (public key only).
        pub_path = (os.environ.get("EDGE_GRANT_PUBLIC_KEY_FILE") or "").strip()
        if pub_path:
            pub = Path(pub_path).read_text(encoding="utf-8")
    if "PRIVATE KEY" in pub:
        raise BranchServiceConfigError(
            "public key material must not contain a private key",
            code="private_key_in_public",
        )

    # Disable .env file loading so host secrets cannot leak into the lab process.
    return Settings(  # type: ignore[call-arg]
        app_env=app_env,
        database_url="",
        jwt_secret="",
        enable_cdn_sync=False,
        enable_branch_cache_control_plane=False,
        enable_edge_grant_issue=False,
        enable_branch_cache_data_plane_sim=True,
        enable_branch_cache_pull_through=True,
        enable_branch_cache_local_serve=True,
        enable_branch_cache_http_service=True,
        enable_branch_cache_http_health=_truthy("ENABLE_BRANCH_CACHE_HTTP_HEALTH"),
        enable_branch_cache_http_metrics=_truthy("ENABLE_BRANCH_CACHE_HTTP_METRICS"),
        enable_branch_cache_http_lab_https_adapter=False,
        enable_branch_cache_http_lab_artifact=True,
        edge_grant_public_key_pem=pub,
        edge_grant_private_key_pem="",
        edge_grant_key_id=(os.environ.get("EDGE_GRANT_KEY_ID") or "lab").strip() or "lab",
        _env_file=None,
    )


def build_lab_config(settings: Settings | None = None) -> BranchServiceConfig:
    settings = settings or load_lab_settings()
    node_id = (os.environ.get("BRANCH_CACHE_NODE_ID") or "").strip()
    site_id = (os.environ.get("BRANCH_CACHE_SITE_ID") or "").strip()
    cache_root = Path(
        (os.environ.get("BRANCH_CACHE_CACHE_ROOT") or "/var/cache/ifilm-branch").strip()
    )
    origin_root = Path(
        (os.environ.get("BRANCH_CACHE_ORIGIN_ROOT") or "/var/lib/ifilm-branch-origin").strip()
    )
    if not origin_root.is_dir():
        raise BranchServiceConfigError(
            "BRANCH_CACHE_ORIGIN_ROOT must be an existing directory",
            code="origin_root",
        )
    # Lab origin is always a fixed local directory — never an arbitrary URL.
    if (os.environ.get("BRANCH_CACHE_ORIGIN_URL") or "").strip():
        raise BranchServiceConfigError(
            "BRANCH_CACHE_ORIGIN_URL is forbidden; use BRANCH_CACHE_ORIGIN_ROOT only",
            code="origin_url_forbidden",
        )
    pub = (settings.edge_grant_public_key_pem or "").strip()
    origin = LocalDirOriginFetcher(origin_root)
    return BranchServiceConfig(
        node_id=node_id,
        site_id=site_id,
        public_key_pem=pub,
        cache_root=cache_root,
        origin=origin,
        settings=settings,
        enable_health=bool(settings.enable_branch_cache_http_health),
        enable_ready=bool(settings.enable_branch_cache_http_health),
        enable_metrics=bool(settings.enable_branch_cache_http_metrics),
        max_concurrent_fills=int(os.environ.get("BRANCH_CACHE_MAX_CONCURRENT_FILLS") or "4"),
    )


def create_app() -> FastAPI:
    """Uvicorn factory: ``uvicorn ...asgi:create_app --factory``."""
    return create_branch_cache_app(build_lab_config())


def validate_lab_startup() -> dict[str, str]:
    """Construct the app without binding a port (CI / network_mode:none smoke)."""
    cfg = build_lab_config()
    app = create_branch_cache_app(cfg)
    # Flatten included routes for a stable smoke signal.
    paths: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            paths.append(str(path))
        for inner in getattr(route, "routes", []) or []:
            ip = getattr(inner, "path", None)
            if ip:
                paths.append(str(ip))
    return {
        "ok": "true",
        "service": "branch-cache-lab",
        "node_id": cfg.node_id,
        "site_id": cfg.site_id,
        "route_paths": ",".join(sorted(set(paths))),
    }
