"""Fail-closed live Radius entitlement gate and production safety tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.core.config import Settings, get_settings
from app.core.runtime import RuntimeConfigurationError, validate_runtime_settings
from app.models.subscriber_auth import SubscriberEntitlementSnapshot
from app.models.user import Subscriber
from app.services.entitlements import check_entitlement
from app.services.identity.provider import _entitlement_from_radius_attrs
from app.services.streaming.eligibility import playback_eligibility
from tests.conftest import TEST_JWT


def _settings(**kwargs) -> Settings:
    base = {
        "app_env": "development",
        "debug": False,
        "jwt_secret": TEST_JWT,
        "database_url": "sqlite://",
        "radius_mode": "live",
        "radius_secret": "unit-test-radius-secret",
        "enable_radius_login": True,
        "subscriber_identity_mode": "radius",
        "radius_enabled": True,
        "radius_entitlement_mapping_enabled": False,
        "radius_mock_users": [],
        "_env_file": None,
    }
    base.update(kwargs)
    return Settings(**base)


def test_fixture_mode_fails_in_production():
    settings = _settings(
        app_env="production",
        jwt_secret="production-grade-jwt-secret-value-32",
        database_url="postgresql+psycopg2://app:strong-unique-secret@db:5432/ifilm",
        subscriber_identity_mode="fixture",
        radius_mode="mock",
        radius_secret="unique-radius-secret-value",
        radius_mock_users=[{"username": "x", "password": "y", "package": "P"}],
    )
    with pytest.raises(RuntimeConfigurationError, match="fixture"):
        validate_runtime_settings(settings)


def test_production_radius_without_mapping_fails_startup():
    settings = _settings(
        app_env="production",
        jwt_secret="production-grade-jwt-secret-value-32",
        database_url="postgresql+psycopg2://app:strong-unique-secret@db:5432/ifilm",
        subscriber_identity_mode="radius",
        radius_entitlement_mapping_enabled=False,
        radius_secret="unique-radius-secret-value",
    )
    with pytest.raises(RuntimeConfigurationError, match="RADIUS_ENTITLEMENT_MAPPING_ENABLED"):
        validate_runtime_settings(settings)


def test_mapping_enabled_requires_attribute_names():
    settings = _settings(
        app_env="development",
        radius_entitlement_mapping_enabled=True,
        radius_attr_package="",
        radius_attr_expiration="",
    )
    with pytest.raises(RuntimeConfigurationError, match="RADIUS_ATTR_PACKAGE"):
        validate_runtime_settings(settings)


def test_access_accept_without_entitlement_attrs_denies_playback(db_session):
    """Access-Accept alone must never grant entitlement/playback."""
    settings = _settings(radius_entitlement_mapping_enabled=False)

    # Simulate Access-Accept path via attribute mapper with no reply attrs
    _account, _service, package, _branch, _until, _max_dev, denial, _reason = _entitlement_from_radius_attrs(
        settings, reply=SimpleNamespace()
    )
    assert denial == "entitlement_unverified"
    assert package is None

    user = Subscriber(
        username="radius_user",
        status="unknown",
        service_status="unknown",
        package="",
        identity_provider="radius",
        external_subject="radius_user",
        max_devices=3,
    )
    db_session.add(user)
    db_session.commit()

    # Provider get_entitlement is unavailable when mapping disabled
    result = check_entitlement(db_session, user, settings=settings, refresh=True)
    assert result.allowed is False
    assert result.denial_code in {"entitlement_unverified", "provider_unavailable", "entitlement_cache_expired"}

    # Playback eligibility must deny
    asset = MagicMock()
    asset.id = "asset-1"
    asset.movie_id = 1
    asset.episode_id = None
    asset.series_id = None
    asset.season_id = None
    elig = playback_eligibility.can_play(db_session, principal=user, media_asset=asset)
    assert elig.allowed is False


def test_missing_mapping_denies_entitlement():
    settings = _settings(radius_entitlement_mapping_enabled=False)
    denial = _entitlement_from_radius_attrs(settings, reply={"Filter-Id": ["x"]})[6]
    assert denial == "entitlement_unverified"


def test_malformed_expiry_denies_entitlement():
    settings = _settings(
        radius_entitlement_mapping_enabled=True,
        radius_attr_package="Filter-Id",
        radius_attr_expiration="Session-Timeout",
    )

    class Reply(dict):
        def __getitem__(self, key):  # noqa: ANN001
            return super().__getitem__(key)

    reply = Reply({"Filter-Id": ["Premium"], "Session-Timeout": ["not-a-date"]})
    denial = _entitlement_from_radius_attrs(settings, reply=reply)[6]
    assert denial == "malformed_expiry"


def test_unknown_package_denies_entitlement():
    settings = _settings(
        radius_entitlement_mapping_enabled=True,
        radius_attr_package="Filter-Id",
        radius_attr_expiration="Session-Timeout",
    )
    reply = {"Filter-Id": ["unknown"], "Session-Timeout": ["2026-12-31"]}
    denial = _entitlement_from_radius_attrs(settings, reply=reply)[6]
    assert denial == "unknown_package"

    reply2 = {"Filter-Id": [""], "Session-Timeout": ["2026-12-31"]}
    denial2 = _entitlement_from_radius_attrs(settings, reply=reply2)[6]
    assert denial2 == "unknown_package"


def test_provider_timeout_denies_without_valid_cache(db_session, monkeypatch):
    settings = _settings(radius_entitlement_mapping_enabled=False)
    user = Subscriber(
        username="to_user",
        status="active",
        service_status="active",
        package="Premium",
        identity_provider="radius",
        external_subject="to_user",
        max_devices=3,
    )
    db_session.add(user)
    db_session.commit()

    def _timeout_entitlement(_subject: str):
        from app.services.identity.provider import EntitlementProviderResult

        return EntitlementProviderResult(
            allowed=False,
            denial_code="provider_unavailable",
            safe_reason="Identity provider unavailable",
            source="radius",
            available=False,
        )

    monkeypatch.setattr(
        "app.services.entitlements.get_identity_provider",
        lambda _cfg=None: SimpleNamespace(get_entitlement=_timeout_entitlement),
    )
    result = check_entitlement(db_session, user, settings=settings, refresh=True)
    assert result.allowed is False
    assert result.denial_code in {"provider_unavailable", "entitlement_cache_expired"}


def test_expired_cache_denies_playback(db_session, monkeypatch):
    settings = get_settings()
    user = Subscriber(
        username="cache_user",
        status="active",
        service_status="active",
        package="Premium",
        identity_provider="radius",
        external_subject="cache_user",
        max_devices=3,
    )
    db_session.add(user)
    db_session.flush()
    now = datetime.now(UTC)
    db_session.add(
        SubscriberEntitlementSnapshot(
            subscriber_id=user.id,
            allowed=True,
            account_status="active",
            service_status="active",
            package_name="Premium",
            branch_code="Kabul",
            valid_until=now + timedelta(days=30),
            max_devices=3,
            source="radius",
            checked_at=now - timedelta(hours=2),
            expires_at=now - timedelta(minutes=1),
        )
    )
    db_session.commit()

    def _unavailable(_subject: str):
        from app.services.identity.provider import EntitlementProviderResult

        return EntitlementProviderResult(
            allowed=False,
            denial_code="provider_unavailable",
            safe_reason="unavailable",
            source="radius",
            available=False,
        )

    monkeypatch.setattr(
        "app.services.entitlements.get_identity_provider",
        lambda _cfg=None: SimpleNamespace(get_entitlement=_unavailable),
    )
    result = check_entitlement(db_session, user, settings=settings, refresh=False)
    assert result.allowed is False
    assert result.denial_code == "entitlement_cache_expired"


def test_malformed_fixture_expiry_denies(client, monkeypatch):
    import json

    monkeypatch.setenv(
        "RADIUS_MOCK_USERS",
        json.dumps(
            [
                {
                    "username": "bad_exp",
                    "password": "bad-exp-pass",
                    "package": "Premium",
                    "branch": "Kabul",
                    "expiration": "not-a-real-date",
                    "account_status": "active",
                    "service_status": "active",
                }
            ]
        ),
    )
    get_settings.cache_clear()
    login = client.post(
        "/api/auth/subscriber/login",
        json={"username": "bad_exp", "password": "bad-exp-pass", "device_id": "be1"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    ent = client.get("/api/me/entitlement", headers={"Authorization": f"Bearer {token}"})
    assert ent.status_code == 200
    assert ent.json()["allowed"] is False
    assert ent.json()["denial_code"] == "malformed_expiry"


def test_unknown_package_fixture_denies(client, monkeypatch):
    import json

    monkeypatch.setenv(
        "RADIUS_MOCK_USERS",
        json.dumps(
            [
                {
                    "username": "unk_pkg",
                    "password": "unk-pkg-pass",
                    "package": "unknown",
                    "branch": "Kabul",
                    "expiration": "2026-12-31",
                    "account_status": "active",
                    "service_status": "active",
                }
            ]
        ),
    )
    get_settings.cache_clear()
    login = client.post(
        "/api/auth/subscriber/login",
        json={"username": "unk_pkg", "password": "unk-pkg-pass", "device_id": "up1"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    ent = client.get("/api/me/entitlement", headers={"Authorization": f"Bearer {token}"})
    assert ent.json()["allowed"] is False
    assert ent.json()["denial_code"] == "unknown_package"


def test_default_provider_mode_is_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_RADIUS_LOGIN", "false")
    monkeypatch.setenv("SUBSCRIBER_IDENTITY_MODE", "disabled")
    monkeypatch.setenv("RADIUS_ENTITLEMENT_MAPPING_ENABLED", "false")
    settings = Settings(
        app_env="production",
        jwt_secret="production-grade-jwt-secret-value-32",
        database_url="postgresql+psycopg2://app:strong-unique-secret@db:5432/ifilm",
        radius_secret="unique-radius-secret-value",
        debug=False,
        enable_radius_login=False,
        subscriber_identity_mode="disabled",
        radius_entitlement_mapping_enabled=False,
        radius_enabled=False,
        radius_mode="live",
        _env_file=None,
    )
    assert settings.subscriber_identity_mode == "disabled"
    assert settings.radius_entitlement_mapping_enabled is False
    validate_runtime_settings(settings)


def test_staging_fixture_allowed_with_opt_in():
    settings = _settings(
        app_env="staging",
        jwt_secret="production-grade-jwt-secret-value-32",
        database_url="postgresql+psycopg2://app:strong-unique-secret@db:5432/ifilm",
        radius_secret="unique-radius-secret-value",
        debug=False,
        subscriber_identity_mode="fixture",
        staging_allow_fixture_auth=True,
        radius_mode="mock",
        radius_entitlement_mapping_enabled=False,
        radius_enabled=False,
        enable_radius_login=True,
        radius_mock_users=[{"username": "x", "password": "y", "package": "P", "expiration": "2027-01-01"}],
    )
    validate_runtime_settings(settings)


def test_production_fixture_still_forbidden_even_with_staging_flag():
    settings = _settings(
        app_env="production",
        jwt_secret="production-grade-jwt-secret-value-32",
        database_url="postgresql+psycopg2://app:strong-unique-secret@db:5432/ifilm",
        radius_secret="unique-radius-secret-value",
        debug=False,
        subscriber_identity_mode="fixture",
        staging_allow_fixture_auth=True,
        radius_mode="mock",
        radius_mock_users=[{"username": "x", "password": "y", "package": "P"}],
    )
    with pytest.raises(RuntimeConfigurationError):
        validate_runtime_settings(settings)
