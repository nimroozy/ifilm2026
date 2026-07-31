"""Phase 11 — subscriber authentication, entitlements, devices, refresh tokens."""

from __future__ import annotations

import json

import pytest
from app.core.config import Settings, get_settings
from app.core.runtime import RuntimeConfigurationError, validate_runtime_settings
from app.models.user import Subscriber
from app.services.identity import GENERIC_FAILURE
from app.services.rate_limit import login_rate_limiter
from tests.conftest import TEST_FIXTURE_PASSWORD, TEST_FIXTURE_USER, TEST_JWT


def _settings(**kwargs) -> Settings:
    base = {
        "app_env": "development",
        "debug": False,
        "jwt_secret": TEST_JWT,
        "database_url": "sqlite://",
        "radius_mode": "mock",
        "radius_secret": "unit-test-radius-secret",
        "enable_radius_login": True,
        "subscriber_identity_mode": "fixture",
        "radius_mock_users": [
            {
                "username": TEST_FIXTURE_USER,
                "password": TEST_FIXTURE_PASSWORD,
                "package": "Premium 50Mbps",
                "branch": "Kabul",
                "expiration": "2026-12-31",
                "service_status": "active",
                "account_status": "active",
                "max_devices": 2,
            }
        ],
        "_env_file": None,
    }
    base.update(kwargs)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    login_rate_limiter.clear()
    yield
    login_rate_limiter.clear()


def test_valid_subscriber_login_returns_refresh(client):
    response = client.post(
        "/api/auth/subscriber/login",
        json={
            "username": TEST_FIXTURE_USER,
            "password": TEST_FIXTURE_PASSWORD,
            "device_id": "dev-primary-001",
            "device_name": "Test Browser",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert "expires_in" in body

    me = client.get("/api/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == TEST_FIXTURE_USER
    assert me.json()["service_status"] == "active"


def test_invalid_login_generic_error(client):
    response = client.post(
        "/api/auth/subscriber/login",
        json={"username": "nope", "password": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_FAILURE


def test_fixture_mode_rejected_in_production():
    settings = _settings(
        app_env="production",
        jwt_secret="production-grade-jwt-secret-value-32",
        database_url="postgresql+psycopg2://app:strong-unique-secret@db:5432/ifilm",
        radius_mode="live",
        subscriber_identity_mode="fixture",
        radius_secret="unique-radius-secret-value",
    )
    with pytest.raises(RuntimeConfigurationError, match="fixture"):
        validate_runtime_settings(settings)


def test_entitlement_active(client):
    login = client.post(
        "/api/auth/subscriber/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD, "device_id": "d1"},
    )
    token = login.json()["access_token"]
    ent = client.get("/api/me/entitlement", headers={"Authorization": f"Bearer {token}"})
    assert ent.status_code == 200
    body = ent.json()
    assert body["allowed"] is True
    assert body["package_name"]
    assert body["branch_code"]


def test_expired_entitlement_denies(client, db_session, monkeypatch):
    users = json.loads(get_settings().model_dump_json() and "[]")  # placate linters
    _ = users
    monkeypatch.setenv(
        "RADIUS_MOCK_USERS",
        json.dumps(
            [
                {
                    "username": "expired_user",
                    "password": "expired-pass-ok",
                    "package": "Basic",
                    "branch": "Kabul",
                    "expiration": "2020-01-01",
                    "service_status": "expired",
                    "account_status": "active",
                }
            ]
        ),
    )
    get_settings.cache_clear()
    # Keep primary fixture too for seed — merge
    monkeypatch.setenv(
        "RADIUS_MOCK_USERS",
        json.dumps(
            [
                {
                    "username": TEST_FIXTURE_USER,
                    "password": TEST_FIXTURE_PASSWORD,
                    "package": "Premium 50Mbps",
                    "branch": "Kabul",
                    "expiration": "2026-12-31",
                    "service_status": "active",
                    "account_status": "active",
                    "max_devices": 2,
                },
                {
                    "username": "expired_user",
                    "password": "expired-pass-ok",
                    "package": "Basic",
                    "branch": "Kabul",
                    "expiration": "2020-01-01",
                    "service_status": "expired",
                    "account_status": "active",
                },
            ]
        ),
    )
    get_settings.cache_clear()

    login = client.post(
        "/api/auth/subscriber/login",
        json={"username": "expired_user", "password": "expired-pass-ok", "device_id": "ex1"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    ent = client.get("/api/me/entitlement", headers={"Authorization": f"Bearer {token}"})
    assert ent.status_code == 200
    assert ent.json()["allowed"] is False
    assert ent.json()["denial_code"] == "service_expired"


def test_suspended_account_entitlement(client, monkeypatch):
    monkeypatch.setenv(
        "RADIUS_MOCK_USERS",
        json.dumps(
            [
                {
                    "username": TEST_FIXTURE_USER,
                    "password": TEST_FIXTURE_PASSWORD,
                    "package": "Premium 50Mbps",
                    "branch": "Kabul",
                    "expiration": "2026-12-31",
                    "service_status": "active",
                    "account_status": "active",
                    "max_devices": 2,
                },
                {
                    "username": "sus_user",
                    "password": "sus-pass-ok",
                    "package": "Premium",
                    "branch": "Kabul",
                    "expiration": "2026-12-31",
                    "service_status": "active",
                    "account_status": "suspended",
                },
            ]
        ),
    )
    get_settings.cache_clear()
    login = client.post(
        "/api/auth/subscriber/login",
        json={"username": "sus_user", "password": "sus-pass-ok", "device_id": "s1"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    ent = client.get("/api/me/entitlement", headers={"Authorization": f"Bearer {token}"})
    assert ent.json()["allowed"] is False
    assert ent.json()["denial_code"] == "account_suspended"


def test_disabled_account_denied_login(client, monkeypatch):
    monkeypatch.setenv(
        "RADIUS_MOCK_USERS",
        json.dumps(
            [
                {
                    "username": TEST_FIXTURE_USER,
                    "password": TEST_FIXTURE_PASSWORD,
                    "package": "Premium 50Mbps",
                    "branch": "Kabul",
                    "expiration": "2026-12-31",
                    "account_status": "active",
                    "service_status": "active",
                },
                {
                    "username": "dis_user",
                    "password": "dis-pass-ok",
                    "package": "Premium",
                    "branch": "Kabul",
                    "expiration": "2026-12-31",
                    "account_status": "disabled",
                    "service_status": "active",
                },
            ]
        ),
    )
    get_settings.cache_clear()
    login = client.post(
        "/api/auth/subscriber/login",
        json={"username": "dis_user", "password": "dis-pass-ok", "device_id": "d1"},
    )
    assert login.status_code == 403
    assert login.json()["detail"]["code"] == "account_disabled"


def test_subscriber_token_denied_admin_apis(client):
    login = client.post(
        "/api/auth/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD},
    )
    token = login.json()["access_token"]
    resp = client.get("/api/admin/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_refresh_rotation_and_reuse(client):
    login = client.post(
        "/api/auth/subscriber/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD, "device_id": "r1"},
    )
    refresh = login.json()["refresh_token"]
    rotated = client.post("/api/auth/subscriber/refresh", json={"refresh_token": refresh})
    assert rotated.status_code == 200
    new_refresh = rotated.json()["refresh_token"]
    assert new_refresh != refresh

    reuse = client.post("/api/auth/subscriber/refresh", json={"refresh_token": refresh})
    assert reuse.status_code == 401
    assert reuse.json()["detail"]["code"] == "refresh_reuse"

    # Family revoked — new token also invalid
    again = client.post("/api/auth/subscriber/refresh", json={"refresh_token": new_refresh})
    assert again.status_code == 401


def test_logout_revokes_refresh(client):
    login = client.post(
        "/api/auth/subscriber/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD, "device_id": "lo1"},
    )
    access = login.json()["access_token"]
    refresh = login.json()["refresh_token"]
    out = client.post(
        "/api/auth/subscriber/logout",
        headers={"Authorization": f"Bearer {access}"},
        json={"refresh_token": refresh},
    )
    assert out.status_code == 200
    denied = client.post("/api/auth/subscriber/refresh", json={"refresh_token": refresh})
    assert denied.status_code == 401


def test_device_limit_and_revoke(client, db_session, monkeypatch):
    monkeypatch.setenv(
        "RADIUS_MOCK_USERS",
        json.dumps(
            [
                {
                    "username": TEST_FIXTURE_USER,
                    "password": TEST_FIXTURE_PASSWORD,
                    "package": "Premium 50Mbps",
                    "branch": "Kabul",
                    "expiration": "2026-12-31",
                    "account_status": "active",
                    "service_status": "active",
                    "max_devices": 2,
                }
            ]
        ),
    )
    get_settings.cache_clear()
    # Ensure local subscriber max_devices reflects fixture on next login
    user = db_session.query(Subscriber).filter(Subscriber.username == TEST_FIXTURE_USER).one_or_none()
    if user:
        user.max_devices = 2
        db_session.add(user)
        db_session.commit()

    a = client.post(
        "/api/auth/subscriber/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD, "device_id": "limit-a"},
    )
    assert a.status_code == 200
    token_a = a.json()["access_token"]

    b = client.post(
        "/api/auth/subscriber/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD, "device_id": "limit-b"},
    )
    assert b.status_code == 200

    c = client.post(
        "/api/auth/subscriber/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD, "device_id": "limit-c"},
    )
    assert c.status_code == 403
    assert c.json()["detail"]["code"] == "device_limit_exceeded"

    devices = client.get("/api/me/devices", headers={"Authorization": f"Bearer {token_a}"})
    assert devices.status_code == 200
    assert len(devices.json()) == 2
    victim = devices.json()[0]["id"]
    revoked = client.delete(f"/api/me/devices/{victim}", headers={"Authorization": f"Bearer {token_a}"})
    assert revoked.status_code == 200

    c2 = client.post(
        "/api/auth/subscriber/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD, "device_id": "limit-c"},
    )
    assert c2.status_code == 200


def test_cross_user_device_idor(client, db_session, monkeypatch):
    monkeypatch.setenv(
        "RADIUS_MOCK_USERS",
        json.dumps(
            [
                {
                    "username": TEST_FIXTURE_USER,
                    "password": TEST_FIXTURE_PASSWORD,
                    "package": "Premium 50Mbps",
                    "branch": "Kabul",
                    "expiration": "2026-12-31",
                    "account_status": "active",
                    "service_status": "active",
                    "max_devices": 3,
                },
                {
                    "username": "other_user",
                    "password": "other-pass-ok",
                    "package": "Standard",
                    "branch": "Kabul",
                    "expiration": "2026-12-31",
                    "account_status": "active",
                    "service_status": "active",
                    "max_devices": 3,
                },
            ]
        ),
    )
    get_settings.cache_clear()

    a = client.post(
        "/api/auth/subscriber/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD, "device_id": "idor-a"},
    )
    b = client.post(
        "/api/auth/subscriber/login",
        json={"username": "other_user", "password": "other-pass-ok", "device_id": "idor-b"},
    )
    devices_a = client.get(
        "/api/me/devices", headers={"Authorization": f"Bearer {a.json()['access_token']}"}
    ).json()
    device_id = devices_a[0]["id"]
    steal = client.delete(
        f"/api/me/devices/{device_id}",
        headers={"Authorization": f"Bearer {b.json()['access_token']}"},
    )
    assert steal.status_code == 404


def test_admin_token_still_works(client, admin_headers):
    me = client.get("/api/admin/auth/me", headers=admin_headers)
    assert me.status_code == 200


def test_passwords_not_stored_after_login(client, db_session):
    client.post(
        "/api/auth/subscriber/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD, "device_id": "pw1"},
    )
    user = db_session.query(Subscriber).filter(Subscriber.username == TEST_FIXTURE_USER).one()
    assert user.hashed_password is None
    assert user.external_subject
    assert user.identity_provider == "fixture"
