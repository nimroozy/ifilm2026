"""Demo seed helpers: artwork, ownership idempotency, demo identity provider."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.runtime import RuntimeConfigurationError, collect_runtime_errors
from app.core.security import hash_password
from app.models.user import Subscriber
from app.services.demo.artwork import write_rgb_png
from app.services.demo.constants import DEMO_SEED_VERSION, PROVIDER_DEMO
from app.services.demo.ownership import DemoOwnership, load_ownership, save_ownership
from app.services.identity.provider import DemoIdentityProvider, get_identity_provider
from tests.conftest import TEST_JWT


def _settings(**kwargs) -> Settings:
    base = {
        "app_env": "production",
        "debug": False,
        "jwt_secret": TEST_JWT,
        "database_url": "postgresql+psycopg://ifilm_ci:ifilm_ci@127.0.0.1:5432/ifilm_ci",
        "playback_token_secret": "playback-token-secret-for-unit-tests-32",
        "enable_local_streaming": True,
        "radius_enabled": False,
        "radius_mode": "live",
        "radius_secret": "not-used-in-demo-mode-but-long-enough",
        "subscriber_identity_mode": "demo",
        "demo_allow_local_auth": True,
        "staging_allow_fixture_auth": False,
        "_env_file": None,
    }
    base.update(kwargs)
    return Settings(**base)


def test_demo_png_placeholder(tmp_path: Path):
    path = tmp_path / "poster.png"
    write_rgb_png(path, 300, 450, (26, 58, 92), "Kabul Nights")
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert path.stat().st_size > 200


def test_ownership_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DEMO_DATA_DIR", str(tmp_path / "demo"))
    settings = _settings(artwork_root=str(tmp_path / "art"))
    ownership = DemoOwnership(seed_version=DEMO_SEED_VERSION, movie_slugs=["demo-kabul-nights"])
    save_ownership(settings, ownership)
    loaded = load_ownership(settings)
    assert loaded.movie_slugs == ["demo-kabul-nights"]
    assert loaded.seed_version == DEMO_SEED_VERSION


def test_demo_mode_runtime_requires_flag():
    settings = _settings(demo_allow_local_auth=False, subscriber_identity_mode="demo")
    errors = collect_runtime_errors(settings)
    assert any("DEMO_ALLOW_LOCAL_AUTH" in e for e in errors)


def test_demo_identity_authenticates_demo_user(db_session):
    settings = _settings()
    user = Subscriber(
        username="demo_active",
        hashed_password=hash_password("demo-password-ok-12"),
        name="Demo Active",
        branch="Kabul",
        status="active",
        package="Demo Premium",
        expiration="2099-01-01",
        identity_provider=PROVIDER_DEMO,
        external_subject="demo_active",
        max_devices=3,
        service_status="active",
    )
    db_session.add(user)
    db_session.commit()

    provider = DemoIdentityProvider(settings)
    ok = provider.authenticate("demo_active", "demo-password-ok-12")
    assert ok.success is True
    assert ok.source == PROVIDER_DEMO
    assert ok.denial_code is None

    bad = provider.authenticate("demo_active", "wrong-password")
    assert bad.success is False

    other = provider.authenticate("not_demo", "demo-password-ok-12")
    assert other.success is False


def test_demo_identity_denies_suspended(db_session):
    settings = _settings()
    db_session.add(
        Subscriber(
            username="demo_suspended",
            hashed_password=hash_password("demo-password-ok-12"),
            name="Demo Suspended",
            status="suspended",
            package="Demo Basic",
            identity_provider=PROVIDER_DEMO,
            external_subject="demo_suspended",
            max_devices=1,
            service_status="inactive",
        )
    )
    db_session.commit()
    provider = get_identity_provider(settings)
    result = provider.authenticate("demo_suspended", "demo-password-ok-12")
    assert result.success is True
    assert result.denial_code == "account_suspended"


def test_demo_provider_rejected_without_flag():
    settings = _settings(demo_allow_local_auth=False)
    with pytest.raises(RuntimeConfigurationError):
        DemoIdentityProvider(settings)
