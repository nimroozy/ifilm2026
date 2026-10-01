"""Regression tests for authoritative artwork CDN publish decisions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.core.config import Settings, get_settings
from app.models.integration_config import IntegrationConfig
from app.services import cdn_management as svc
from app.services.integration_secrets import encrypt_secret
from app.services.object_storage.artwork_cdn import (
    evaluate_artwork_cdn_effective,
    publish_artwork_file,
)
from app.services.object_storage.factory import get_artwork_cdn_storage
from cryptography.fernet import Fernet


def _settings(**kwargs) -> Settings:
    base = dict(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        artwork_root="/tmp/ifilm-test-artwork-cdn-decision",
        enable_artwork_cdn_sync=False,
    )
    base.update(kwargs)
    return Settings(**base)


@pytest.fixture
def encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATION_SECRETS_KEY", key)
    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


def _seed_storage_row(
    db_session,
    *,
    encryption_key: str,
    enabled: bool,
    artwork_cdn_enabled: bool,
    public_base_url: str = "https://cdn.example.com",
    with_credentials: bool = True,
):
    ciphertext = None
    if with_credentials:
        ciphertext = encrypt_secret(
            plaintext='{"access_key_id":"ak","secret_access_key":"sk"}',
            master_key=encryption_key,
        )
    row = IntegrationConfig(
        provider=svc.R2_PROVIDER,
        enabled=enabled,
        secret_ciphertext=ciphertext,
        config_json={
            "provider": "cloudflare_r2",
            "endpoint_url": "https://acct.r2.cloudflarestorage.com",
            "account_id": "acct",
            "bucket": "ifilm-art",
            "region": "auto",
            "object_key_prefix": "ifilm",
            "public_base_url": public_base_url,
            "artwork_cdn_enabled": artwork_cdn_enabled,
        },
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_a_host_flag_false_blocks_admin_artwork(db_session, encryption_key, tmp_path: Path):
    _seed_storage_row(db_session, encryption_key=encryption_key, enabled=False, artwork_cdn_enabled=True)
    settings = _settings(
        enable_artwork_cdn_sync=False,
        artwork_cdn_public_base_url="https://cdn.example.com",
        integration_secrets_key=encryption_key,
    )
    state = evaluate_artwork_cdn_effective(settings, db=db_session)
    assert state.host_capability is False
    assert state.admin_requested is True
    assert state.effective is False
    assert state.publishing_status == "blocked_by_server_capability"
    store = MagicMock()
    src = tmp_path / "p.jpg"
    src.write_bytes(b"\xff\xd8\xff" + b"0" * 8)
    assert publish_artwork_file(
        relative_path="posters/x.jpg", source=src, settings=settings, db=db_session, storage=store
    ) is None
    store.put_file.assert_not_called()
    assert get_artwork_cdn_storage(settings, db=db_session) is None


def test_b_admin_artwork_false_even_when_hot_tier_enabled(
    db_session, encryption_key, tmp_path: Path, monkeypatch
):
    """CRITICAL: row.enabled must not enable artwork publishing."""
    _seed_storage_row(db_session, encryption_key=encryption_key, enabled=True, artwork_cdn_enabled=False)
    settings = _settings(
        enable_artwork_cdn_sync=True,
        artwork_cdn_public_base_url="https://cdn.example.com",
        r2_endpoint_url="https://env.r2.cloudflarestorage.com",
        r2_bucket="env-bucket",
        r2_access_key_id="env-ak",
        r2_secret_access_key="env-sk",
        integration_secrets_key=encryption_key,
    )
    state = evaluate_artwork_cdn_effective(settings, db=db_session)
    assert state.admin_requested is False
    assert state.effective is False
    assert state.publishing_status == "disabled"
    assert svc.resolve_r2_credentials_for_artwork(db_session, settings) is None
    assert get_artwork_cdn_storage(settings, db=db_session) is None
    store = MagicMock()
    src = tmp_path / "p.jpg"
    src.write_bytes(b"\xff\xd8\xff" + b"0" * 8)
    assert publish_artwork_file(
        relative_path="posters/x.jpg", source=src, settings=settings, db=db_session, storage=store
    ) is None
    store.put_file.assert_not_called()


def test_c_artwork_works_with_hot_tier_disabled(db_session, encryption_key, tmp_path: Path):
    _seed_storage_row(db_session, encryption_key=encryption_key, enabled=False, artwork_cdn_enabled=True)
    settings = _settings(
        enable_artwork_cdn_sync=True,
        integration_secrets_key=encryption_key,
    )
    state = evaluate_artwork_cdn_effective(settings, db=db_session)
    assert state.effective is True
    assert state.publishing_status == "active"
    assert get_artwork_cdn_storage(settings, db=db_session) is not None
    store = MagicMock()
    store.exists.side_effect = [False, True]
    src = tmp_path / "p.jpg"
    src.write_bytes(b"\xff\xd8\xff" + b"0" * 8)
    result = publish_artwork_file(
        relative_path="posters/tmdb-poster-1-abcdef123456.jpg",
        source=src,
        settings=settings,
        db=db_session,
        storage=store,
    )
    assert result is not None
    assert result.public_url.startswith("https://cdn.example.com/")
    store.put_file.assert_called_once()


def test_d_missing_credentials_not_ready(db_session, encryption_key):
    _seed_storage_row(
        db_session,
        encryption_key=encryption_key,
        enabled=False,
        artwork_cdn_enabled=True,
        with_credentials=False,
    )
    settings = _settings(enable_artwork_cdn_sync=True, integration_secrets_key=encryption_key)
    state = evaluate_artwork_cdn_effective(settings, db=db_session)
    assert state.credentials_configured is False
    assert state.effective is False
    assert get_artwork_cdn_storage(settings, db=db_session) is None


def test_e_missing_public_base_not_ready(db_session, encryption_key):
    _seed_storage_row(
        db_session,
        encryption_key=encryption_key,
        enabled=False,
        artwork_cdn_enabled=True,
        public_base_url="",
    )
    settings = _settings(
        enable_artwork_cdn_sync=True,
        artwork_cdn_public_base_url="",
        integration_secrets_key=encryption_key,
    )
    state = evaluate_artwork_cdn_effective(settings, db=db_session)
    assert state.public_base_configured is False
    assert state.effective is False


def test_f_legacy_env_only_without_admin_row():
    settings = _settings(
        enable_artwork_cdn_sync=True,
        artwork_cdn_public_base_url="https://cdn.example.com",
        r2_endpoint_url="https://acct.r2.cloudflarestorage.com",
        r2_bucket="art",
        r2_access_key_id="k",
        r2_secret_access_key="s",
    )
    state = evaluate_artwork_cdn_effective(settings, db=None)
    assert state.has_admin_row is False
    assert state.effective is True
    assert state.publishing_status == "active"
    assert get_artwork_cdn_storage(settings, db=None) is not None


def test_g_toggle_off_stops_next_publish(db_session, encryption_key, tmp_path: Path):
    row = _seed_storage_row(
        db_session, encryption_key=encryption_key, enabled=False, artwork_cdn_enabled=True
    )
    settings = _settings(enable_artwork_cdn_sync=True, integration_secrets_key=encryption_key)
    assert evaluate_artwork_cdn_effective(settings, db=db_session).effective is True
    data = dict(row.config_json or {})
    data["artwork_cdn_enabled"] = False
    row.config_json = data
    db_session.add(row)
    db_session.commit()
    store = MagicMock()
    src = tmp_path / "p.jpg"
    src.write_bytes(b"\xff\xd8\xff" + b"0" * 8)
    assert publish_artwork_file(
        relative_path="posters/x.jpg", source=src, settings=settings, db=db_session, storage=store
    ) is None
    store.put_file.assert_not_called()


def test_h_no_sdk_when_effective_false(db_session, encryption_key, tmp_path: Path):
    _seed_storage_row(db_session, encryption_key=encryption_key, enabled=True, artwork_cdn_enabled=False)
    settings = _settings(enable_artwork_cdn_sync=True, integration_secrets_key=encryption_key)
    store = MagicMock()
    src = tmp_path / "p.jpg"
    src.write_bytes(b"x")
    assert publish_artwork_file(
        relative_path="posters/x.jpg", source=src, settings=settings, db=db_session, storage=store
    ) is None
    store.exists.assert_not_called()
    store.put_file.assert_not_called()


def test_get_r2_reports_effective_status(client, admin_headers, encryption_key, monkeypatch):
    monkeypatch.setenv("ENABLE_ARTWORK_CDN_SYNC", "false")
    get_settings.cache_clear()
    put = client.put(
        "/api/admin/cdn-management/r2",
        headers=admin_headers,
        json={
            "enabled": False,
            "provider": "cloudflare_r2",
            "account_id": "acct",
            "bucket": "ifilm-art",
            "region": "auto",
            "public_base_url": "https://cdn.example.com",
            "artwork_cdn_enabled": True,
            "access_key_id": "k",
            "secret_access_key": "s",
        },
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["endpoint_url"] == "https://acct.r2.cloudflarestorage.com"
    assert body["artwork_cdn_requested"] is True
    assert body["artwork_cdn_host_capability"] is False
    assert body["artwork_cdn_effective"] is False
    assert body["artwork_publishing_status"] == "blocked_by_server_capability"
    get_settings.cache_clear()
