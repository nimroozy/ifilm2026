"""Admin-managed Portal integration settings."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.admin import AdminUser
from app.models.integration_config import IntegrationConfig
from app.services.integration_secrets import IntegrationSecretsError, encrypt_secret
from app.services.portal.client import probe_portal_connection
from app.services.portal.config_resolver import (
    PORTAL_PROVIDER,
    invalidate_portal_config_cache,
    resolve_portal_runtime_config,
    resolve_portal_token,
)
from app.services.portal.url_validation import (
    PortalUrlValidationError,
    validate_api_prefix,
    validate_portal_base_url,
)

logger = logging.getLogger(__name__)

DEFAULT_PORTAL_CONFIG: dict[str, Any] = {
    "base_url": "https://portal.mns.af",
    "api_prefix": "/api/voice-ai/v1",
    "client": "ifilm",
    "request_source": "ifilm",
    "connect_timeout_seconds": 3,
    "read_timeout_seconds": 5,
    "entitlement_ttl_seconds": 900,
}


class PortalSettingsError(ValueError):
    pass


def _audit(event: str, *, admin_id: int) -> None:
    logger.info("portal_admin_event event=%s admin_id=%s", event, admin_id)


def _get_or_create_row(db: Session) -> IntegrationConfig:
    row = db.query(IntegrationConfig).filter(IntegrationConfig.provider == PORTAL_PROVIDER).one_or_none()
    if row is None:
        row = IntegrationConfig(provider=PORTAL_PROVIDER, enabled=False, config_json=dict(DEFAULT_PORTAL_CONFIG))
        db.add(row)
        db.flush()
    return row


def _token_configured(row: IntegrationConfig | None, settings: Settings) -> bool:
    env_cfg = resolve_portal_runtime_config(None, settings, use_cache=False)
    if row is None:
        return env_cfg.token_configured
    token = resolve_portal_token(
        secret_ciphertext=row.secret_ciphertext,
        settings=settings,
        env_token=env_cfg.token,
    )
    return bool(token)


def _public_config(row: IntegrationConfig, settings: Settings) -> dict[str, Any]:
    data = dict(row.config_json or DEFAULT_PORTAL_CONFIG)
    updated_at = row.updated_at
    if updated_at and updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return {
        "enabled": bool(row.enabled),
        "base_url": str(data.get("base_url") or DEFAULT_PORTAL_CONFIG["base_url"]),
        "api_prefix": str(data.get("api_prefix") or DEFAULT_PORTAL_CONFIG["api_prefix"]),
        "client": str(data.get("client") or DEFAULT_PORTAL_CONFIG["client"]),
        "request_source": str(data.get("request_source") or DEFAULT_PORTAL_CONFIG["request_source"]),
        "connect_timeout_seconds": float(
            data.get("connect_timeout_seconds") or DEFAULT_PORTAL_CONFIG["connect_timeout_seconds"]
        ),
        "read_timeout_seconds": float(
            data.get("read_timeout_seconds") or DEFAULT_PORTAL_CONFIG["read_timeout_seconds"]
        ),
        "entitlement_ttl_seconds": int(
            data.get("entitlement_ttl_seconds") or DEFAULT_PORTAL_CONFIG["entitlement_ttl_seconds"]
        ),
        "token_configured": _token_configured(row, settings),
        "updated_at": updated_at.isoformat() if updated_at else None,
        "last_test_at": data.get("last_test_at"),
        "last_test_ok": data.get("last_test_ok"),
        "last_test_http_status": data.get("last_test_http_status"),
        "last_test_portal_reachable": data.get("last_test_portal_reachable"),
        "last_test_credential_accepted": data.get("last_test_credential_accepted"),
    }


def get_portal_settings(db: Session, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    row = db.query(IntegrationConfig).filter(IntegrationConfig.provider == PORTAL_PROVIDER).one_or_none()
    if row is None:
        env = resolve_portal_runtime_config(None, cfg, use_cache=False)
        return {
            "enabled": env.enabled,
            "base_url": env.base_url,
            "api_prefix": env.api_prefix,
            "client": env.client,
            "request_source": env.request_source,
            "connect_timeout_seconds": env.connect_timeout_seconds,
            "read_timeout_seconds": env.read_timeout_seconds,
            "entitlement_ttl_seconds": env.entitlement_cache_ttl_seconds,
            "token_configured": env.token_configured,
            "updated_at": None,
            "last_test_at": None,
            "last_test_ok": None,
            "last_test_http_status": None,
            "last_test_portal_reachable": None,
            "last_test_credential_accepted": None,
            "config_source": env.source,
        }
    out = _public_config(row, cfg)
    out["config_source"] = "db"
    return out


def update_portal_settings(
    db: Session,
    admin: AdminUser,
    *,
    payload: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    row = _get_or_create_row(db)
    data = dict(row.config_json or DEFAULT_PORTAL_CONFIG)

    if "enabled" in payload and payload["enabled"] is not None:
        row.enabled = bool(payload["enabled"])

    if payload.get("base_url") is not None:
        try:
            data["base_url"] = validate_portal_base_url(str(payload["base_url"]), app_env=cfg.app_env)
        except PortalUrlValidationError as exc:
            raise PortalSettingsError(str(exc)) from exc
    if payload.get("api_prefix") is not None:
        try:
            data["api_prefix"] = validate_api_prefix(str(payload["api_prefix"]))
        except PortalUrlValidationError as exc:
            raise PortalSettingsError(str(exc)) from exc
    if payload.get("client") is not None:
        data["client"] = str(payload["client"]).strip() or "ifilm"
    if payload.get("request_source") is not None:
        data["request_source"] = str(payload["request_source"]).strip() or "ifilm"
    if payload.get("connect_timeout_seconds") is not None:
        data["connect_timeout_seconds"] = max(1, min(60, int(payload["connect_timeout_seconds"])))
    if payload.get("read_timeout_seconds") is not None:
        data["read_timeout_seconds"] = max(1, min(120, int(payload["read_timeout_seconds"])))
    if payload.get("entitlement_ttl_seconds") is not None:
        data["entitlement_ttl_seconds"] = max(60, min(86400, int(payload["entitlement_ttl_seconds"])))

    remove_token = bool(payload.get("remove_token"))
    token = payload.get("token")
    if remove_token:
        row.secret_ciphertext = None
        _audit("portal_token_removed", admin_id=admin.id)
    elif token is not None and str(token).strip():
        master = (cfg.integration_secrets_key or "").strip()
        if not master:
            raise PortalSettingsError(
                "Integration encryption key is not configured on the server. "
                "Set INTEGRATION_SECRETS_KEY before storing a Portal token."
            )
        try:
            row.secret_ciphertext = encrypt_secret(plaintext=str(token), master_key=master)
        except IntegrationSecretsError as exc:
            raise PortalSettingsError("Unable to store Portal token securely.") from exc
        _audit("portal_token_replaced", admin_id=admin.id)

    row.config_json = data
    row.updated_by_admin_id = admin.id
    row.updated_at = datetime.now(UTC)

    if row.enabled and not _token_configured(row, cfg):
        raise PortalSettingsError(
            "Portal authentication cannot be enabled without a configured service token."
        )

    try:
        validate_portal_base_url(str(data.get("base_url") or ""), app_env=cfg.app_env)
        validate_api_prefix(str(data.get("api_prefix") or ""))
    except PortalUrlValidationError as exc:
        raise PortalSettingsError(str(exc)) from exc

    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_portal_config_cache()
    _audit("portal_settings_updated", admin_id=admin.id)
    if row.enabled:
        _audit("portal_auth_enabled", admin_id=admin.id)
    else:
        _audit("portal_auth_disabled", admin_id=admin.id)
    return get_portal_settings(db, cfg)


def test_portal_connection(db: Session, admin: AdminUser, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    row = db.query(IntegrationConfig).filter(IntegrationConfig.provider == PORTAL_PROVIDER).one_or_none()
    runtime = resolve_portal_runtime_config(db, cfg, use_cache=False)

    if not runtime.token_configured:
        raise PortalSettingsError("Configure a Portal service token before testing the connection.")

    result = probe_portal_connection(runtime)
    now_iso = datetime.now(UTC).isoformat()

    if row is not None:
        data = dict(row.config_json or DEFAULT_PORTAL_CONFIG)
        data["last_test_at"] = now_iso
        data["last_test_ok"] = bool(result.get("ok"))
        data["last_test_http_status"] = result.get("http_status")
        data["last_test_portal_reachable"] = result.get("portal_reachable")
        data["last_test_credential_accepted"] = result.get("credential_accepted")
        row.config_json = data
        row.updated_by_admin_id = admin.id
        row.updated_at = datetime.now(UTC)
        db.add(row)
        db.commit()

    _audit("portal_connection_tested", admin_id=admin.id)
    return result

