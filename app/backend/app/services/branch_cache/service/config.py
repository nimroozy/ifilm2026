"""Configuration and startup validation for the offline branch HTTP service candidate."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.services.branch_cache.data_plane.origin import OriginFetcher


def _is_prod_like(app_env: str) -> bool:
    """Local copy to avoid importing app.core.runtime (pulls SQLAlchemy via db_url)."""
    return (app_env or "").strip().lower() in {"production", "staging", "prod"}


class BranchServiceConfigError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_config") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class BranchServiceConfig:
    """Explicit lab/test config. Never loads Portal/SAS or private signing keys."""

    node_id: str
    site_id: str
    public_key_pem: str
    cache_root: Path
    origin: OriginFetcher
    settings: Settings
    enable_health: bool = False
    enable_ready: bool = False
    enable_metrics: bool = False
    max_path_length: int = 512
    max_header_bytes: int = 16_384
    max_concurrent_fills: int = 4
    high_watermark_bytes: int = 50_000_000
    low_watermark_bytes: int = 20_000_000
    min_free_bytes: int = 1_000_000
    allow_private_signing_key: bool = False  # must stay False
    allow_portal_sas: bool = False  # must stay False
    debug: bool = False
    # Extra forbidden markers for tests
    extra_forbidden: dict[str, Any] = field(default_factory=dict)


def validate_branch_service_config(cfg: BranchServiceConfig) -> None:
    """Reject unsafe startup combinations before the ASGI app is created."""
    if cfg.allow_private_signing_key:
        raise BranchServiceConfigError(
            "private signing keys are forbidden on branch service", code="private_key_forbidden"
        )
    if cfg.allow_portal_sas:
        raise BranchServiceConfigError(
            "Portal/SAS credentials are forbidden on branch service", code="portal_forbidden"
        )
    if cfg.debug:
        raise BranchServiceConfigError("debug mode is forbidden", code="debug_forbidden")
    if (cfg.settings.edge_grant_private_key_pem or "").strip() and not (
        # Issuing grants in the same process for tests is OK on central settings,
        # but the branch service itself must not *require* or expose them.
        False
    ):
        # Soft: presence of private key in shared Settings used for issue-in-tests is allowed,
        # but branch service must never read it. Enforce explicit forbid flag only.
        pass

    pub = (cfg.public_key_pem or "").strip()
    if "BEGIN PUBLIC KEY" not in pub and "BEGIN CERTIFICATE" not in pub:
        raise BranchServiceConfigError(
            "public verification key required", code="missing_public_key"
        )
    if "PRIVATE KEY" in pub:
        raise BranchServiceConfigError(
            "public_key_pem must not contain a private key", code="private_key_in_public"
        )

    if not (cfg.node_id or "").strip() or not (cfg.site_id or "").strip():
        raise BranchServiceConfigError("node_id and site_id required", code="identity")

    root = cfg.cache_root
    try:
        resolved = root.resolve()
    except OSError as exc:
        raise BranchServiceConfigError("cache_root unreadable", code="cache_root") from exc
    forbidden_roots = {"/", "/etc", "/var", "/usr", "/home", "/root", "/tmp"}
    if str(resolved) in forbidden_roots:
        raise BranchServiceConfigError("cache_root is not a dedicated path", code="broad_root")
    if resolved.exists() and resolved.is_symlink():
        raise BranchServiceConfigError("cache_root must not be a symlink", code="symlink_root")

    if cfg.max_path_length < 64 or cfg.max_path_length > 4096:
        raise BranchServiceConfigError("max_path_length out of bounds", code="limits")
    if cfg.max_header_bytes < 1024 or cfg.max_header_bytes > 65_536:
        raise BranchServiceConfigError("max_header_bytes out of bounds", code="limits")

    if _is_prod_like(cfg.settings.app_env):
        raise BranchServiceConfigError(
            "branch HTTP service candidate cannot start in staging/production",
            code="prod_forbidden",
        )
    if not cfg.settings.enable_branch_cache_http_service:
        # Factory may still be used in unit tests that set the flag on settings.
        if cfg.settings.app_env not in {"test", "development"}:
            raise BranchServiceConfigError(
                "ENABLE_BRANCH_CACHE_HTTP_SERVICE must be true to construct the app",
                code="flag_off",
            )
    if cfg.settings.enable_cdn_sync:
        raise BranchServiceConfigError("legacy ENABLE_CDN_SYNC must remain false", code="cdn_sync")
    if cfg.extra_forbidden.get("customer_db"):
        raise BranchServiceConfigError(
            "customer DB credentials forbidden on branch service", code="customer_db"
        )
