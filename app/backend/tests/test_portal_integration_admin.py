"""Admin Portal integration settings — encryption, API, runtime resolver."""

from __future__ import annotations

import httpx
import pytest
from app.core.config import get_settings
from app.models.integration_config import IntegrationConfig
from app.services.admin import portal_integration as svc
from app.services.integration_secrets import IntegrationSecretsError, decrypt_secret, encrypt_secret
from app.services.portal.client import probe_portal_connection
from app.services.portal.config_resolver import (
    PORTAL_PROVIDER,
    invalidate_portal_config_cache,
    resolve_portal_runtime_config,
)
from app.services.portal.runtime_config import PortalRuntimeConfig
from app.services.portal.url_validation import PortalUrlValidationError, validate_portal_base_url
from cryptography.fernet import Fernet


@pytest.fixture
def integration_master_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATION_SECRETS_KEY", key)
    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


def _admin_headers(client, monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "unit-test-admin-pass-ok")
    get_settings.cache_clear()
    login = client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": "unit-test-admin-pass-ok"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_encrypt_decrypt_roundtrip(integration_master_key):
    ct = encrypt_secret(plaintext="test-portal-token-not-real", master_key=integration_master_key)
    assert decrypt_secret(ciphertext=ct, master_key=integration_master_key) == "test-portal-token-not-real"
    assert b"test-portal-token" not in ct


def test_missing_master_key_blocks_encrypt():
    with pytest.raises(IntegrationSecretsError):
        encrypt_secret(plaintext="x", master_key="")


def test_get_portal_settings_never_returns_token(client, db_session, integration_master_key, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    resp = client.get("/api/admin/integrations/portal", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "token" not in body
    assert "secret" not in str(body).lower() or "token_configured" in body
    assert "ciphertext" not in body


def test_admin_auth_required_for_portal_settings(client):
    assert client.get("/api/admin/integrations/portal").status_code == 401


def test_create_and_update_portal_settings(client, db_session, integration_master_key, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    put = client.put(
        "/api/admin/integrations/portal",
        headers=headers,
        json={
            "base_url": "https://portal.mns.af",
            "api_prefix": "/api/voice-ai/v1",
            "client": "ifilm",
            "request_source": "ifilm",
            "token": "stored-test-token-not-real",
            "enabled": False,
        },
    )
    assert put.status_code == 200
    data = put.json()
    assert data["token_configured"] is True
    assert "token" not in data

    row = db_session.query(IntegrationConfig).filter(IntegrationConfig.provider == PORTAL_PROVIDER).one()
    assert row.secret_ciphertext is not None
    assert b"stored-test-token" not in row.secret_ciphertext

    put2 = client.put(
        "/api/admin/integrations/portal",
        headers=headers,
        json={"client": "ifilm-updated"},
    )
    assert put2.status_code == 200
    assert put2.json()["client"] == "ifilm-updated"
    assert put2.json()["token_configured"] is True

    db_session.expire_all()
    runtime = resolve_portal_runtime_config(db_session, get_settings(), use_cache=False)
    assert runtime.client == "ifilm-updated"
    assert runtime.token == "stored-test-token-not-real"


def test_enable_without_token_rejected(client, db_session, integration_master_key, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    resp = client.put(
        "/api/admin/integrations/portal",
        headers=headers,
        json={"enabled": True},
    )
    assert resp.status_code == 400


def test_invalid_base_url_rejected(client, integration_master_key, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    resp = client.put(
        "/api/admin/integrations/portal",
        headers=headers,
        json={"base_url": "http://127.0.0.1"},
    )
    assert resp.status_code == 400


def test_localhost_ssrf_rejected():
    with pytest.raises(PortalUrlValidationError):
        validate_portal_base_url("https://localhost", app_env="production")


def test_runtime_env_fallback(db_session, monkeypatch):
    monkeypatch.setenv("PORTAL_AUTH_ENABLED", "true")
    monkeypatch.setenv("PORTAL_VOICE_AI_TOKEN", "env-token-not-real")
    get_settings.cache_clear()
    runtime = resolve_portal_runtime_config(db_session, get_settings(), use_cache=False)
    assert runtime.source == "env"
    assert runtime.token == "env-token-not-real"
    assert runtime.enabled is True


def test_connection_test_mock_valid_bearer(integration_master_key):
    config = PortalRuntimeConfig(
        enabled=False,
        base_url="https://portal.example.test",
        api_prefix="/api/voice-ai/v1",
        token="probe-token-not-real",
        client="ifilm",
        request_source="ifilm",
        connect_timeout_seconds=3.0,
        read_timeout_seconds=5.0,
        entitlement_cache_ttl_seconds=900,
        source="env",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in str(request.headers).lower() or "Bearer" in request.headers.get(
            "authorization", ""
        )
        return httpx.Response(
            200,
            json={"success": True, "verified": False, "code": "verification_failed"},
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        result = probe_portal_connection(config, http_client=http_client)
    assert result["credential_accepted"] is True
    assert result["portal_reachable"] is True


def test_connection_test_invalid_bearer(integration_master_key):
    config = PortalRuntimeConfig(
        enabled=False,
        base_url="https://portal.example.test",
        api_prefix="/api/voice-ai/v1",
        token="bad-token-not-real",
        client="ifilm",
        request_source="ifilm",
        connect_timeout_seconds=3.0,
        read_timeout_seconds=5.0,
        entitlement_cache_ttl_seconds=900,
        source="env",
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"success": False, "code": "unauthorized"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        result = probe_portal_connection(config, http_client=http_client)
    assert result["credential_accepted"] is False


def test_missing_master_key_blocks_token_save(client, db_session, monkeypatch):
    monkeypatch.delenv("INTEGRATION_SECRETS_KEY", raising=False)
    get_settings.cache_clear()
    headers = _admin_headers(client, monkeypatch)
    resp = client.put(
        "/api/admin/integrations/portal",
        headers=headers,
        json={"token": "should-not-store-not-real"},
    )
    assert resp.status_code == 400
    assert "INTEGRATION_SECRETS_KEY" in resp.json()["detail"] or "encryption" in resp.json()["detail"].lower()


def test_http_base_url_rejected_in_production(client, integration_master_key, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    headers = _admin_headers(client, monkeypatch)
    resp = client.put(
        "/api/admin/integrations/portal",
        headers=headers,
        json={"base_url": "http://portal.mns.af"},
    )
    assert resp.status_code == 400


def test_connection_test_endpoint(client, db_session, integration_master_key, monkeypatch):
    headers = _admin_headers(client, monkeypatch)
    client.put(
        "/api/admin/integrations/portal",
        headers=headers,
        json={"token": "probe-token-not-real", "enabled": False},
    )

    monkeypatch.setattr(
        svc,
        "probe_portal_connection",
        lambda _config: {
            "ok": True,
            "portal_reachable": True,
            "credential_accepted": True,
            "http_status": 200,
            "message": "Portal reachable and credentials accepted.",
        },
    )

    resp = client.post("/api/admin/integrations/portal/test", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["credential_accepted"] is True
    assert "token" not in body


def test_settings_permission_required(client, monkeypatch):
    assert client.get("/api/admin/integrations/portal").status_code == 401


def test_cache_invalidated_on_update(db_session, integration_master_key, monkeypatch):
    monkeypatch.setenv("PORTAL_VOICE_AI_TOKEN", "env-fallback-token")
    get_settings.cache_clear()
    from app.models.admin import AdminUser

    admin = db_session.query(AdminUser).filter(AdminUser.username == "admin").one()
    svc.update_portal_settings(
        db_session,
        admin,
        payload={"token": "db-token-not-real", "enabled": False},
    )
    invalidate_portal_config_cache()
    runtime = resolve_portal_runtime_config(db_session, get_settings(), use_cache=False)
    assert runtime.token == "db-token-not-real"
