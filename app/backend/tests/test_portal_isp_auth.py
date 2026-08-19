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


def test_expired_offline_login_denied(client, db_session, monkeypatch):
    """LIVE_QA: expired + internet_status=offline must deny (no username fallback)."""
    _portal_settings(monkeypatch)
    monkeypatch.setattr(
        "app.services.subscriber_auth.lookup_customer",
        _mock_lookup(
            _active_customer(
                account_status="expired",
                internet_status="offline",
                expiry_date="2026-08-09",
                days_remaining=-10,
                branch="Kabul",
            )
        ),
    )
    resp = client.post(
        "/api/auth/isp/login",
        json={"branch": "Kabul", "username": "1210000", "password": "secret-pass"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "service_expired"
    assert (
        db_session.query(Subscriber)
        .filter(Subscriber.identity_provider == PROVIDER_PORTAL)
        .count()
        == 0
    )


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


def test_verification_failed_password_is_generic_401(client, monkeypatch):
    """LIVE_QA: invalid password → HTTP 200 verification_failed → generic 401."""
    _portal_settings(monkeypatch)
    monkeypatch.setattr(
        "app.services.subscriber_auth.lookup_customer",
        _mock_lookup(
            {
                "success": True,
                "verified": False,
                "code": "verification_failed",
                "message": "The customer information could not be verified.",
            },
            status_code=200,
        ),
    )
    resp = client.post(
        "/api/auth/isp/login",
        json={"branch": "Nimruz", "username": "1210000", "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "invalid_credentials"
    assert "password" not in resp.json()["detail"]["message"].lower()


def test_verification_failed_username_is_same_generic_401(client, monkeypatch):
    """LIVE_QA: invalid username is indistinguishable from invalid password."""
    _portal_settings(monkeypatch)
    monkeypatch.setattr(
        "app.services.subscriber_auth.lookup_customer",
        _mock_lookup(
            {
                "success": True,
                "verified": False,
                "code": "verification_failed",
                "message": "The customer information could not be verified.",
            },
            status_code=200,
        ),
    )
    resp = client.post(
        "/api/auth/isp/login",
        json={"branch": "Nimruz", "username": "qa-nonexistent-000000", "password": "x"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "invalid_credentials"


@pytest.mark.parametrize(
    "status,code",
    [
        ("expired", "service_expired"),
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


def test_external_subject_uses_customer_number():
    assert external_subject_for(branch="Nimruz", customer_number="1210000") == "NMZ:1210000"
    assert external_subject_for(branch="Kabul", customer_number="1210000") == "KBL:1210000"
    assert external_subject_for(branch="KBL", customer_number="1210000") == "KBL:1210000"


def test_numeric_location_id_rejected(client, monkeypatch):
    """Numeric HTML ids are not valid iFilm / S2S branch values."""
    _portal_settings(monkeypatch)

    def _should_not_call(*args, **kwargs):
        raise AssertionError("portal lookup must not run for numeric branch id")

    monkeypatch.setattr("app.services.subscriber_auth.lookup_customer", _should_not_call)
    resp = client.post(
        "/api/auth/isp/login",
        json={"branch": "1", "username": "1210000", "password": "secret-pass"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "invalid_credentials"


def test_missing_customer_number_fail_closed(client, db_session, monkeypatch):
    """Verified active payload without customer_number must not create a subscriber."""
    _portal_settings(monkeypatch)
    body = _active_customer()
    body["customer"].pop("customer_number", None)
    monkeypatch.setattr(
        "app.services.subscriber_auth.lookup_customer",
        _mock_lookup(body),
    )
    resp = client.post(
        "/api/auth/isp/login",
        json={"branch": "Nimruz", "username": "1210000", "password": "secret-pass"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "provider_unavailable"
    assert (
        db_session.query(Subscriber)
        .filter(Subscriber.identity_provider == PROVIDER_PORTAL)
        .count()
        == 0
    )


def test_identity_uses_customer_number_not_username(client, db_session, monkeypatch):
    """external_subject is {CODE}:{customer_number}, not the typed username."""
    _portal_settings(monkeypatch)
    monkeypatch.setattr(
        "app.services.subscriber_auth.lookup_customer",
        _mock_lookup(_active_customer(customer_number="9911223", branch="Nimruz")),
    )
    resp = client.post(
        "/api/auth/isp/login",
        json={"branch": "Nimruz", "username": "typed-username", "password": "x"},
    )
    assert resp.status_code == 200
    user = (
        db_session.query(Subscriber)
        .filter(Subscriber.identity_provider == PROVIDER_PORTAL)
        .one()
    )
    assert user.external_subject == "NMZ:9911223"
    assert user.username == "typed-username"


def test_same_customer_number_kbl_and_nmz_are_distinct(client, db_session, monkeypatch):
    _portal_settings(monkeypatch)

    def payload(*, branch, username, password):
        return _active_customer(branch=branch, customer_number="1210000")

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
    subjects = {
        r.external_subject
        for r in db_session.query(Subscriber).filter(Subscriber.identity_provider == PROVIDER_PORTAL)
    }
    assert subjects == {"NMZ:1210000", "KBL:1210000"}


def test_portal_identity_unique_constraint(db_session, client):
    """Same (provider, external_subject) cannot be inserted twice."""
    from sqlalchemy.exc import IntegrityError

    db_session.add(
        Subscriber(
            username="1210000",
            identity_provider=PROVIDER_PORTAL,
            external_subject="NMZ:1210000",
            name="A",
        )
    )
    db_session.commit()
    db_session.add(
        Subscriber(
            username="1210000",
            identity_provider=PROVIDER_PORTAL,
            external_subject="NMZ:1210000",
            name="B",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_portal_identity_branch_scoped_subjects_coexist(db_session, client):
    """Same username in different branches → different external_subject, both valid."""
    db_session.add_all(
        [
            Subscriber(
                username="1210000",
                identity_provider=PROVIDER_PORTAL,
                external_subject="NMZ:1210000",
                name="Nimruz",
                branch="Nimruz",
            ),
            Subscriber(
                username="1210000",
                identity_provider=PROVIDER_PORTAL,
                external_subject="KBL:1210000",
                name="Kabul",
                branch="Kabul",
            ),
        ]
    )
    db_session.commit()
    rows = (
        db_session.query(Subscriber)
        .filter(Subscriber.username == "1210000", Subscriber.identity_provider == PROVIDER_PORTAL)
        .all()
    )
    assert {r.external_subject for r in rows} == {"NMZ:1210000", "KBL:1210000"}


def test_local_null_external_subjects_coexist(db_session, client):
    """Ordinary local subscribers with external_subject=NULL may coexist."""
    db_session.add_all(
        [
            Subscriber(username="local_a", identity_provider="local", external_subject=None),
            Subscriber(username="local_b", identity_provider="local", external_subject=None),
            Subscriber(username="local_c", identity_provider="local", external_subject=None),
        ]
    )
    db_session.commit()
    assert (
        db_session.query(Subscriber)
        .filter(Subscriber.identity_provider == "local", Subscriber.external_subject.is_(None))
        .count()
        >= 3
    )


def test_portal_upsert_matches_provider_subject_not_username(db_session, client, monkeypatch):
    """Upsert finds existing portal row by provider+subject, not global username."""
    from app.core.config import get_settings
    from app.services.identity.provider import IdentityAuthResult
    from app.services.subscriber_auth import upsert_subscriber_from_identity

    _portal_settings(monkeypatch)
    existing = Subscriber(
        username="1210000",
        identity_provider=PROVIDER_PORTAL,
        external_subject="NMZ:1210000",
        name="Original",
        branch="Nimruz",
    )
    # Decoy: same username, different branch subject — must not be overwritten.
    decoy = Subscriber(
        username="1210000",
        identity_provider=PROVIDER_PORTAL,
        external_subject="KBL:1210000",
        name="Decoy Kabul",
        branch="Kabul",
    )
    db_session.add_all([existing, decoy])
    db_session.commit()
    existing_id = existing.id
    decoy_id = decoy.id

    identity = IdentityAuthResult(
        success=True,
        external_subject="NMZ:1210000",
        display_name="Updated Name",
        account_status="active",
        service_status="unknown",
        package_name="L1",
        branch_code="Nimruz",
        source=PROVIDER_PORTAL,
    )
    user = upsert_subscriber_from_identity(
        db_session,
        username="1210000",
        identity=identity,
        settings=get_settings(),
    )
    db_session.commit()
    assert user.id == existing_id
    assert user.name == "Updated Name"
    decoy_row = db_session.get(Subscriber, decoy_id)
    assert decoy_row is not None
    assert decoy_row.name == "Decoy Kabul"
    assert decoy_row.external_subject == "KBL:1210000"


def test_concurrent_first_login_integrity_error_refetch(db_session, client, monkeypatch):
    """Race on first insert: IntegrityError → re-fetch existing identity, no unhandled 500."""
    from app.core.config import get_settings
    from app.services import subscriber_auth as auth_mod
    from app.services.identity.provider import IdentityAuthResult
    from app.services.subscriber_auth import upsert_subscriber_from_identity

    _portal_settings(monkeypatch)
    winner = Subscriber(
        username="1210000",
        identity_provider=PROVIDER_PORTAL,
        external_subject="NMZ:1210000",
        name="Winner",
        branch="Nimruz",
    )
    db_session.add(winner)
    db_session.commit()
    winner_id = winner.id

    identity = IdentityAuthResult(
        success=True,
        external_subject="NMZ:1210000",
        display_name="Recovered",
        account_status="active",
        service_status="unknown",
        package_name="L1",
        branch_code="Nimruz",
        source=PROVIDER_PORTAL,
    )

    # Simulate concurrent SELECT miss: first lookup sees nothing, insert races.
    real_find = auth_mod._find_by_provider_subject
    calls = {"n": 0}

    def _find(db, *, provider_name, external):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real_find(db, provider_name=provider_name, external=external)

    monkeypatch.setattr(auth_mod, "_find_by_provider_subject", _find)

    user = upsert_subscriber_from_identity(
        db_session,
        username="1210000",
        identity=identity,
        settings=get_settings(),
    )
    db_session.commit()
    assert user.id == winner_id
    assert user.name == "Recovered"
    assert (
        db_session.query(Subscriber)
        .filter(
            Subscriber.identity_provider == PROVIDER_PORTAL,
            Subscriber.external_subject == "NMZ:1210000",
        )
        .count()
        == 1
    )


def test_login_sends_canonical_branch_name(client, monkeypatch):
    _portal_settings(monkeypatch)
    seen: dict = {}

    def _fn(settings, *, branch, username, password, http_client=None):
        seen["branch"] = branch
        return _mock_lookup(_active_customer(branch="Nimruz"))(
            settings, branch=branch, username=username, password=password, http_client=http_client
        )

    monkeypatch.setattr("app.services.subscriber_auth.lookup_customer", _fn)
    resp = client.post(
        "/api/auth/isp/login",
        json={"branch": "NMZ", "username": "1210000", "password": "x"},
    )
    assert resp.status_code == 200
    assert seen["branch"] == "Nimruz"


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
