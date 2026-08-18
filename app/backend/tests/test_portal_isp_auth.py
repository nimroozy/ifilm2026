"""A1 portal ISP authentication — mocked portal Voice AI responses."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from app.core.config import get_settings
from app.models.user import Subscriber
from app.services.entitlements import check_entitlement
from app.services.portal import PROVIDER_PORTAL, external_subject_for
from app.services.rate_limit import login_rate_limiter


def _portal_settings(monkeypatch, **extra):
    values = {
        "subscriber_identity_mode": "portal",
        "portal_auth_enabled": True,
        "portal_voice_ai_token": "test-portal-token-not-real",
        "portal_voice_ai_client": "3cx-voice-agent",
        "portal_request_source": "3cx_voice",
        "portal_entitlement_cache_ttl_seconds": 900,
        "entitlement_cache_ttl_seconds": 900,
        "portal_login_rate_limit": 20,
        "portal_login_rate_window_seconds": 300,
    }
    values.update(extra)
    monkeypatch.setenv("SUBSCRIBER_IDENTITY_MODE", str(values["subscriber_identity_mode"]))
    monkeypatch.setenv(
        "PORTAL_AUTH_ENABLED",
        "true" if values["portal_auth_enabled"] else "false",
    )
    monkeypatch.setenv("PORTAL_VOICE_AI_TOKEN", str(values["portal_voice_ai_token"]))
    monkeypatch.setenv("PORTAL_VOICE_AI_CLIENT", str(values["portal_voice_ai_client"]))
    monkeypatch.setenv("PORTAL_REQUEST_SOURCE", str(values["portal_request_source"]))
    monkeypatch.setenv(
        "PORTAL_ENTITLEMENT_CACHE_TTL_SECONDS",
        str(values["portal_entitlement_cache_ttl_seconds"]),
    )
    monkeypatch.setenv("ENTITLEMENT_CACHE_TTL_SECONDS", str(values["entitlement_cache_ttl_seconds"]))
    monkeypatch.setenv("PORTAL_LOGIN_RATE_LIMIT", str(values["portal_login_rate_limit"]))
    monkeypatch.setenv(
        "PORTAL_LOGIN_RATE_WINDOW_SECONDS",
        str(values["portal_login_rate_window_seconds"]),
    )
    get_settings.cache_clear()
    return get_settings()


def _active_customer(**overrides):
    customer = {
        "display_name": "Haroon Rashidi",
        "customer_number": "1210000",
        "branch": "Nimruz",
        "account_status": "active",
        "internet_status": "offline",
        "current_package": {
            "name": "L1-85 GB | 3Mbps | 1Month",
            "download_speed": "3 Mbps",
            "upload_speed": "",
        },
        "expiry_date": "2026-08-23",
        "days_remaining": 4,
        "balance_due": 600,
        "currency": "AFN",
    }
    customer.update(overrides)
    return {
        "success": True,
        "verified": True,
        "customer": customer,
    }


@pytest.fixture(autouse=True)
def _clear_limiter():
    login_rate_limiter.clear()
    yield
    login_rate_limiter.clear()


def _mock_lookup(payload: dict, status_code: int = 200):
    def _fn(settings, *, branch, username, password, http_client=None):
        from app.services.portal.client import PortalLookupResult

        assert password != ""  # password must be sent to portal, never empty
        _ = settings, http_client
        body = payload
        if callable(payload):
            body = payload(branch=branch, username=username, password=password)
        return PortalLookupResult(
            success=bool(body.get("success")),
            verified=bool(body.get("verified")),
            customer=body.get("customer") if isinstance(body.get("customer"), dict) else None,
            http_status=status_code,
            portal_code=body.get("code"),
        )

    return _fn


def test_isp_locations(client, monkeypatch):
    _portal_settings(monkeypatch)
    resp = client.get("/api/auth/isp/locations")
    assert resp.status_code == 200
    names = [loc["name"] for loc in resp.json()["locations"]]
    assert names == ["Kabul", "Kandahar", "Ghazni", "Nimruz", "Buldak", "Helmand"]
    assert all(loc["active"] for loc in resp.json()["locations"])
    assert all("code" in loc for loc in resp.json()["locations"])


def test_isp_locations_disabled(client, monkeypatch):
    _portal_settings(monkeypatch, portal_auth_enabled=False)
    monkeypatch.setenv("PORTAL_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    resp = client.get("/api/auth/isp/locations")
    assert resp.status_code == 503


def test_active_offline_login_succeeds(client, db_session, monkeypatch):
    _portal_settings(monkeypatch)
    monkeypatch.setattr(
        "app.services.subscriber_auth.lookup_customer",
        _mock_lookup(_active_customer()),
    )
    resp = client.post(
        "/api/auth/isp/login",
        json={"branch": "Nimruz", "username": "1210000", "password": "secret-pass"},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]
    user = (
        db_session.query(Subscriber)
        .filter(Subscriber.external_subject == "NMZ:1210000")
        .one()
    )
    assert user.identity_provider == PROVIDER_PORTAL
    assert user.username == "1210000"
    assert user.hashed_password is None
    assert user.name == "Haroon Rashidi"
    assert user.branch == "Nimruz"
    assert user.status == "active"


def test_wrong_credentials(client, monkeypatch):
    _portal_settings(monkeypatch)
    monkeypatch.setattr(
        "app.services.subscriber_auth.lookup_customer",
        _mock_lookup(
            {"success": False, "verified": False, "code": "password_rejected"},
            status_code=422,
        ),
    )
    resp = client.post(
        "/api/auth/isp/login",
        json={"branch": "Nimruz", "username": "1210000", "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "invalid_credentials"


@pytest.mark.parametrize(
    "status,code",
    [
        ("expired", "service_expired"),
        ("disabled", "account_disabled"),
        ("unknown", "entitlement_unverified"),
        ("weird_future_status", "entitlement_unverified"),
    ],
)
def test_non_active_account_denied(client, monkeypatch, status, code):
    _portal_settings(monkeypatch)
    monkeypatch.setattr(
        "app.services.subscriber_auth.lookup_customer",
        _mock_lookup(_active_customer(account_status=status)),
    )
    resp = client.post(
        "/api/auth/isp/login",
        json={"branch": "Nimruz", "username": "1210000", "password": "secret-pass"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == code


def test_branch_scoped_duplicate_usernames(client, db_session, monkeypatch):
    _portal_settings(monkeypatch)

    def payload(*, branch, username, password):
        return _active_customer(branch=branch, customer_number=username)

    monkeypatch.setattr(
        "app.services.subscriber_auth.lookup_customer",
        _mock_lookup(payload),
    )
    a = client.post(
        "/api/auth/isp/login",
        json={"branch": "Nimruz", "username": "1210000", "password": "a"},
    )
    b = client.post(
        "/api/auth/isp/login",
        json={"branch": "Kabul", "username": "1210000", "password": "a"},
    )
    assert a.status_code == 200
    assert b.status_code == 200
    rows = (
        db_session.query(Subscriber)
        .filter(Subscriber.username == "1210000", Subscriber.identity_provider == PROVIDER_PORTAL)
        .all()
    )
    subjects = {r.external_subject for r in rows}
    assert subjects == {"NMZ:1210000", "KBL:1210000"}
    assert len(rows) == 2


def test_password_never_persisted(client, db_session, monkeypatch):
    _portal_settings(monkeypatch)
    monkeypatch.setattr(
        "app.services.subscriber_auth.lookup_customer",
        _mock_lookup(_active_customer()),
    )
    client.post(
        "/api/auth/isp/login",
        json={"branch": "Nimruz", "username": "1210000", "password": "never-store-me"},
    )
    user = db_session.query(Subscriber).filter(Subscriber.external_subject == "NMZ:1210000").one()
    assert user.hashed_password is None
    # Ensure password string is not accidentally stored in any text column
    blob = f"{user.name}|{user.username}|{user.package}|{user.branch}|{user.expiration}"
    assert "never-store-me" not in blob


def test_portal_timeout(client, monkeypatch):
    _portal_settings(monkeypatch)

    def boom(*args, **kwargs):
        from app.services.portal.client import PortalClientError

        raise PortalClientError(
            "provider_unavailable",
            "Authentication service is temporarily unavailable. Please try again.",
        )

    monkeypatch.setattr("app.services.subscriber_auth.lookup_customer", boom)
    resp = client.post(
        "/api/auth/isp/login",
        json={"branch": "Nimruz", "username": "1210000", "password": "x"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "provider_unavailable"


def test_entitlement_ttl_15_minutes(client, db_session, monkeypatch):
    _portal_settings(monkeypatch)
    monkeypatch.setattr(
        "app.services.subscriber_auth.lookup_customer",
        _mock_lookup(_active_customer()),
    )
    login = client.post(
        "/api/auth/isp/login",
        json={"branch": "Nimruz", "username": "1210000", "password": "x"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    user = db_session.query(Subscriber).filter(Subscriber.external_subject == "NMZ:1210000").one()

    fresh = check_entitlement(db_session, user, settings=get_settings())
    assert fresh.allowed is True
    assert fresh.from_cache is True

    # Expire the snapshot
    from app.models.subscriber_auth import SubscriberEntitlementSnapshot

    snap = (
        db_session.query(SubscriberEntitlementSnapshot)
        .filter(SubscriberEntitlementSnapshot.subscriber_id == user.id)
        .order_by(SubscriberEntitlementSnapshot.checked_at.desc())
        .first()
    )
    assert snap is not None
    snap.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    snap.checked_at = datetime.now(UTC) - timedelta(minutes=20)
    db_session.add(snap)
    db_session.commit()

    stale = check_entitlement(db_session, user, settings=get_settings())
    assert stale.allowed is False
    assert stale.denial_code in {"entitlement_cache_expired", "provider_unavailable"}

    # Admin login unaffected
    admin = client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": "unit-test-admin-pass-ok"},
    )
    assert admin.status_code == 200
    _ = token


def test_admin_login_unaffected_when_portal_enabled(client, monkeypatch):
    _portal_settings(monkeypatch)
    resp = client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": "unit-test-admin-pass-ok"},
    )
    assert resp.status_code == 200


def test_external_subject_helper():
    assert external_subject_for(branch="Nimruz", username="1210000") == "NMZ:1210000"
    assert external_subject_for(branch="Kabul", username="1210000") == "KBL:1210000"


def test_client_sends_3cx_request_source(monkeypatch):
    _portal_settings(monkeypatch)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["json"] = httpx.Response(200, request=request).request  # placeholder
        import json

        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_active_customer())

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        from app.services.portal.client import lookup_customer

        result = lookup_customer(
            get_settings(),
            branch="Nimruz",
            username="1210000",
            password="pw",
            http_client=http_client,
        )
    assert result.success is True
    assert captured["body"]["request_source"] == "3cx_voice"
    assert captured["headers"]["x-mobin-client"] == "3cx-voice-agent"
    assert "pw" not in str(captured["headers"])
