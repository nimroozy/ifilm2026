from datetime import UTC, datetime, timedelta

import pytest
from app.core.config import Settings
from app.core.runtime import (
    RuntimeConfigurationError,
    require_admin_bootstrap_password,
    validate_runtime_settings,
)
from app.services.radius import GENERIC_FAILURE, RadiusService
from app.services.readiness import readiness_report
from jose import jwt
from tests.conftest import TEST_FIXTURE_PASSWORD, TEST_FIXTURE_USER, TEST_JWT


def _settings(**kwargs) -> Settings:
    base = {
        "app_env": "development",
        "debug": False,
        "jwt_secret": TEST_JWT,
        "database_url": "sqlite://",
        "radius_mode": "mock",
        "radius_secret": "unit-test-radius-secret",
        "enable_radius_login": False,
        "radius_mock_users": [],
        "_env_file": None,
    }
    base.update(kwargs)
    return Settings(**base)


def test_production_rejects_default_jwt_secret():
    settings = _settings(
        app_env="production",
        jwt_secret="change-me-in-production",
        database_url="postgresql+psycopg2://app:strong-unique-secret@db:5432/ifilm",
        radius_mode="live",
        radius_secret="unique-radius-secret-value",
    )
    with pytest.raises(RuntimeConfigurationError, match="JWT_SECRET"):
        validate_runtime_settings(settings)


def test_production_rejects_mock_radius():
    settings = _settings(
        app_env="production",
        jwt_secret="production-grade-jwt-secret-value-32",
        database_url="postgresql+psycopg2://app:strong-unique-secret@db:5432/ifilm",
        radius_mode="mock",
        radius_secret="unique-radius-secret-value",
        enable_radius_login=True,
        radius_mock_users=[{"username": "x", "password": "y"}],
    )
    with pytest.raises(RuntimeConfigurationError, match="RADIUS_MODE=mock"):
        validate_runtime_settings(settings)


def test_arbitrary_mock_credentials_are_rejected(client):
    denied = RadiusService().authenticate("random_user", "random_pass")
    assert denied.success is False
    assert denied.message == GENERIC_FAILURE

    response = client.post(
        "/api/auth/login",
        json={"username": "random_user", "password": "random_pass"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_FAILURE


def test_admin_bootstrap_requires_explicit_credentials():
    with pytest.raises(RuntimeConfigurationError, match="ADMIN_BOOTSTRAP_PASSWORD"):
        require_admin_bootstrap_password(_settings(admin_bootstrap_password=None))

    with pytest.raises(RuntimeConfigurationError, match="unsafe default"):
        require_admin_bootstrap_password(_settings(admin_bootstrap_password="admin123"))


def test_invalid_login_returns_generic_error(client):
    admin = client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert admin.status_code == 401
    assert admin.json()["detail"] == "Invalid credentials"

    subscriber = client.post(
        "/api/auth/login",
        json={"username": TEST_FIXTURE_USER, "password": "wrong-password"},
    )
    assert subscriber.status_code == 401
    assert subscriber.json()["detail"] == GENERIC_FAILURE


def test_protected_admin_endpoint_rejects_subscriber_token(client):
    login = client.post(
        "/api/auth/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.get("/api/admin/auth/me", headers=headers)
    assert response.status_code == 403


def test_expired_token_is_rejected(client):
    payload = {
        "sub": "1",
        "typ": "admin",
        "exp": datetime.now(UTC) - timedelta(minutes=5),
    }
    token = jwt.encode(payload, TEST_JWT, algorithm="HS256")
    response = client.get("/api/admin/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_upload_size_limit_is_enforced(client, admin_headers, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("UPLOAD_MAX_BYTES", "1024")
    get_settings.cache_clear()
    response = client.post(
        "/api/admin/uploads",
        headers=admin_headers,
        json={"filename": "big.mp4", "content_type": "movie", "size_bytes": 2048},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "File too large"
    monkeypatch.delenv("UPLOAD_MAX_BYTES", raising=False)
    get_settings.cache_clear()


def test_invalid_media_type_is_rejected(client, admin_headers):
    created = client.post(
        "/api/admin/uploads",
        headers=admin_headers,
        json={"filename": "clip.mp4", "content_type": "movie", "size_bytes": 100},
    )
    assert created.status_code == 201
    upload_id = created.json()["id"]
    response = client.post(
        f"/api/admin/uploads/{upload_id}/file",
        headers=admin_headers,
        files={"file": ("clip.mp4", b"data", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid media type"


def test_path_traversal_filenames_are_rejected(client, admin_headers):
    response = client.post(
        "/api/admin/uploads",
        headers=admin_headers,
        json={"filename": "../etc/passwd", "content_type": "movie", "size_bytes": 10},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid filename"

    created = client.post(
        "/api/admin/uploads",
        headers=admin_headers,
        json={"filename": "ok.mp4", "content_type": "movie", "size_bytes": 10},
    )
    assert created.status_code == 201
    nested = client.post(
        f"/api/admin/uploads/{created.json()['id']}/file",
        headers=admin_headers,
        files={"file": ("../../evil.mp4", b"data", "video/mp4")},
    )
    assert nested.status_code == 400
    assert nested.json()["detail"] == "Invalid filename"


def test_redis_readiness_failure_is_reported(monkeypatch):
    from app.services import readiness as readiness_module

    monkeypatch.setattr(readiness_module, "check_database", lambda: {"ok": True})
    monkeypatch.setattr(
        readiness_module,
        "check_redis",
        lambda settings: {"ok": False, "error": "redis_unavailable", "detail": "ConnectionError"},
    )
    settings = _settings(redis_required=True)
    report = readiness_report(settings)
    assert report["status"] == "not_ready"
    assert report["redis"]["ok"] is False
    assert report["redis"]["error"] == "redis_unavailable"
