"""Environment-driven configuration for the CDN node runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import Settings

_FORBIDDEN_ENV = (
    "EDGE_GRANT_PRIVATE_KEY_PEM",
    "DATABASE_URL",
    "REDIS_URL",
    "POSTGRES_PASSWORD",
    "JWT_SECRET",
    "PLAYBACK_TOKEN_SECRET",
    "ADMIN_BOOTSTRAP_PASSWORD",
    "RADIUS_SECRET",
    "AWS_SECRET_ACCESS_KEY",
    "R2_SECRET_ACCESS_KEY",
    "MEDIA_ORIGIN_SECRET_ACCESS_KEY",
    "INTEGRATION_SECRETS_KEY",
    "PORTAL_CLIENT_SECRET",
)


class NodeRuntimeError(ValueError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class NodeRuntimeConfig:
    node_id: str
    role: str
    site_id: str
    central_url: str
    node_token: str = field(repr=False)
    cache_root: Path
    cache_limit_bytes: int
    high_watermark_bytes: int
    low_watermark_bytes: int
    bind_host: str
    bind_port: int
    public_key_pem: str
    edge_grant_key_id: str
    software_version: str
    heartbeat_seconds: int = 30
    max_object_bytes: int = 64 * 1024 * 1024
    max_concurrent_fills: int = 4
    connect_timeout_seconds: float = 3.0
    read_timeout_seconds: float = 20.0

    def __repr__(self) -> str:
        return f"NodeRuntimeConfig(node_id={self.node_id!r}, role={self.role!r}, site_id={self.site_id!r})"


def load_node_runtime_config(env: dict[str, str] | None = None) -> NodeRuntimeConfig:
    src = dict(os.environ if env is None else env)
    if not _truthy(src.get("ENABLE_CDN_NODE_SERVICE")):
        raise NodeRuntimeError("ENABLE_CDN_NODE_SERVICE must be true on CDN nodes", code="flag_off")
    if _truthy(src.get("ENABLE_CDN_SYNC")):
        raise NodeRuntimeError("legacy ENABLE_CDN_SYNC must remain false", code="cdn_sync")
    present = [k for k in _FORBIDDEN_ENV if (src.get(k) or "").strip()]
    if present:
        raise NodeRuntimeError(
            "central secrets must never be present on a CDN node: " + ",".join(present),
            code="secrets_forbidden",
        )
    node_id = (src.get("IFILM_CDN_NODE_ID") or "").strip()
    token = (src.get("IFILM_CDN_NODE_TOKEN") or "").strip()
    central = (src.get("IFILM_CDN_CENTRAL_URL") or "").strip().rstrip("/")
    if not node_id or not token:
        raise NodeRuntimeError("IFILM_CDN_NODE_ID and IFILM_CDN_NODE_TOKEN are required", code="identity")
    parsed = urlparse(central)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query:
        raise NodeRuntimeError("IFILM_CDN_CENTRAL_URL must be a plain https URL", code="central_url")
    role = (src.get("IFILM_CDN_NODE_ROLE") or "cache").strip().lower()
    if role not in {"main", "cache"}:
        raise NodeRuntimeError("IFILM_CDN_NODE_ROLE must be main or cache", code="role")
    cache_root = Path((src.get("IFILM_CDN_CACHE_ROOT") or "/var/lib/ifilm-cdn/cache").strip())
    if str(cache_root) in {"/", "/etc", "/var", "/usr", "/home", "/root", "/tmp"}:
        raise NodeRuntimeError("IFILM_CDN_CACHE_ROOT must be a dedicated directory", code="cache_root")
    try:
        limit = int(src.get("IFILM_CDN_CACHE_LIMIT_BYTES") or "0")
        high = int(src.get("IFILM_CDN_HIGH_WATERMARK_BYTES") or (limit * 90 // 100))
        low = int(src.get("IFILM_CDN_LOW_WATERMARK_BYTES") or (limit * 80 // 100))
        port = int(src.get("IFILM_CDN_BIND_PORT") or "8443")
        heartbeat = int(src.get("IFILM_CDN_HEARTBEAT_SECONDS") or "30")
    except ValueError as exc:
        raise NodeRuntimeError("numeric node settings are invalid", code="numeric") from exc
    if limit <= 0 or not (0 < low < high <= limit):
        raise NodeRuntimeError("cache limit/watermarks must satisfy 0 < low < high <= limit", code="limits")
    if not 1 <= port <= 65535:
        raise NodeRuntimeError("IFILM_CDN_BIND_PORT out of range", code="port")
    public_pem = (src.get("IFILM_CDN_EDGE_GRANT_PUBLIC_KEY_PEM") or "").strip()
    key_file = (src.get("IFILM_CDN_EDGE_GRANT_PUBLIC_KEY_FILE") or "").strip()
    if not public_pem and key_file and Path(key_file).is_file():
        public_pem = Path(key_file).read_text(encoding="utf-8").strip()
    if "PRIVATE KEY" in public_pem:
        raise NodeRuntimeError("edge-grant material on a node must be the public key only", code="private_key")
    return NodeRuntimeConfig(
        node_id=node_id,
        role=role,
        site_id=(src.get("IFILM_CDN_SITE_ID") or "default").strip().lower() or "default",
        central_url=central,
        node_token=token,
        cache_root=cache_root,
        cache_limit_bytes=limit,
        high_watermark_bytes=high,
        low_watermark_bytes=low,
        bind_host=(src.get("IFILM_CDN_BIND_HOST") or "0.0.0.0").strip(),
        bind_port=port,
        public_key_pem=public_pem,
        edge_grant_key_id=(src.get("IFILM_CDN_EDGE_GRANT_KEY_ID") or "eg1").strip() or "eg1",
        software_version=(src.get("IFILM_CDN_SOFTWARE_VERSION") or "unknown").strip()[:64],
        heartbeat_seconds=max(10, min(300, heartbeat)),
        max_object_bytes=int(src.get("IFILM_CDN_MAX_OBJECT_BYTES") or 64 * 1024 * 1024),
        max_concurrent_fills=max(1, min(64, int(src.get("IFILM_CDN_MAX_CONCURRENT_FILLS") or "4"))),
    )


def node_settings(cfg: NodeRuntimeConfig) -> Settings:
    """Minimal in-process Settings for the data plane (no .env, no DB, no secrets)."""
    return Settings(  # type: ignore[call-arg]
        app_env="cdn-node",
        database_url="",
        jwt_secret="",
        enable_cdn_sync=False,
        enable_branch_cache_control_plane=False,
        enable_edge_grant_issue=False,
        enable_branch_cache_data_plane_sim=True,
        enable_branch_cache_pull_through=True,
        enable_branch_cache_local_serve=True,
        enable_branch_cache_http_service=True,
        enable_branch_cache_http_health=True,
        enable_branch_cache_http_metrics=True,
        edge_grant_public_key_pem=cfg.public_key_pem,
        edge_grant_private_key_pem="",
        edge_grant_key_id=cfg.edge_grant_key_id,
        _env_file=None,
    )
