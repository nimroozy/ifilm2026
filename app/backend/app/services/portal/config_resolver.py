"""Resolve Portal runtime settings from DB with environment fallback."""

from __future__ import annotations

import logging
import threading
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.integration_config import IntegrationConfig
from app.services.integration_secrets import IntegrationSecretsError, decrypt_secret
from app.services.portal.runtime_config import PortalRuntimeConfig

logger = logging.getLogger(__name__)

PORTAL_PROVIDER = "portal_mns"

_cache_lock = threading.Lock()
_cache_version = 0
_cached: PortalRuntimeConfig | None = None
_cached_version = -1


def invalidate_portal_config_cache() -> None:
    global _cache_version, _cached, _cached_version
    with _cache_lock:
        _cache_version += 1
        _cached = None
        _cached_version = -1


def _env_portal_config(settings: Settings) -> PortalRuntimeConfig:
    return PortalRuntimeConfig(
        enabled=bool(settings.portal_auth_enabled),
        base_url=(settings.portal_base_url or "https://portal.mns.af").strip(),
        api_prefix=(settings.portal_voice_ai_prefix or "/api/voice-ai/v1").strip(),
        token=(settings.portal_voice_ai_token or "").strip(),
        client=(settings.portal_voice_ai_client or "ifilm").strip(),
        request_source=(settings.portal_request_source or "ifilm").strip(),
        connect_timeout_seconds=float(settings.portal_connect_timeout_seconds),
        read_timeout_seconds=float(settings.portal_read_timeout_seconds),
        entitlement_cache_ttl_seconds=int(settings.portal_entitlement_cache_ttl_seconds or 900),
        source="env",
    )


def _default_portal_config() -> PortalRuntimeConfig:
    return PortalRuntimeConfig(
        enabled=False,
        base_url="https://portal.mns.af",
        api_prefix="/api/voice-ai/v1",
        token="",
        client="ifilm",
        request_source="ifilm",
        connect_timeout_seconds=3.0,
        read_timeout_seconds=5.0,
        entitlement_cache_ttl_seconds=900,
        source="default",
    )


def _coerce_config_field(config: dict[str, Any], key: str, fallback: Any) -> Any:
    if key not in config or config[key] is None:
        return fallback
    return config[key]


def resolve_portal_runtime_config(
    db: Session | None,
    settings: Settings | None = None,
    *,
    use_cache: bool = True,
) -> PortalRuntimeConfig:
    global _cached, _cached_version
    cfg = settings or get_settings()

    if use_cache:
        with _cache_lock:
            if _cached is not None and _cached_version == _cache_version:
                return _cached

    env_cfg = _env_portal_config(cfg)
    if db is None:
        resolved = env_cfg
    else:
        row = db.query(IntegrationConfig).filter(IntegrationConfig.provider == PORTAL_PROVIDER).one_or_none()
        if row is None:
            resolved = env_cfg
        else:
            data = dict(row.config_json or {})
            token = ""
            if row.secret_ciphertext:
                master = (cfg.integration_secrets_key or "").strip()
                if master:
                    try:
                        token = decrypt_secret(ciphertext=row.secret_ciphertext, master_key=master)
                    except IntegrationSecretsError:
                        logger.warning("portal_runtime_token_decrypt_unavailable")
                        token = ""
                else:
                    logger.warning("portal_runtime_missing_integration_secrets_key")

            if not token:
                token = env_cfg.token

            resolved = PortalRuntimeConfig(
                enabled=bool(row.enabled),
                base_url=str(_coerce_config_field(data, "base_url", env_cfg.base_url)).strip(),
                api_prefix=str(_coerce_config_field(data, "api_prefix", env_cfg.api_prefix)).strip(),
                token=token.strip(),
                client=str(_coerce_config_field(data, "client", env_cfg.client)).strip(),
                request_source=str(_coerce_config_field(data, "request_source", env_cfg.request_source)).strip(),
                connect_timeout_seconds=float(
                    _coerce_config_field(data, "connect_timeout_seconds", env_cfg.connect_timeout_seconds)
                ),
                read_timeout_seconds=float(
                    _coerce_config_field(data, "read_timeout_seconds", env_cfg.read_timeout_seconds)
                ),
                entitlement_cache_ttl_seconds=int(
                    _coerce_config_field(
                        data, "entitlement_ttl_seconds", env_cfg.entitlement_cache_ttl_seconds
                    )
                ),
                source="db",
            )

    if use_cache:
        with _cache_lock:
            _cached = resolved
            _cached_version = _cache_version

    return resolved
