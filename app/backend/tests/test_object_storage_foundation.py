"""Unit tests for hybrid CDN / object-storage Phase 1 foundation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.core.config import Settings
from app.core.runtime import collect_runtime_errors
from app.services.object_storage.factory import (
    get_central_origin_storage,
    get_hot_tier_storage,
    get_local_workspace_storage,
)
from app.services.object_storage.keys import ObjectKeyBuilder, StorageObjectKind
from app.services.object_storage.local import LocalFilesystemStorage
from app.services.object_storage.s3_compatible import S3CompatibleConfig, S3CompatibleStorage
from app.services.object_storage.status import safe_storage_status
from app.services.object_storage.tiers import StorageProviderKind, StorageRole
from app.services.object_storage.validation import collect_object_storage_errors


def test_object_key_builder_conventions():
    keys = ObjectKeyBuilder(prefix="ifilm")
    assert keys.original_key(asset_id="a1", stored_filename="a1.mp4") == "ifilm/v1/originals/a1/a1.mp4"
    assert keys.package_root(asset_id="a1", package_id="p9") == "ifilm/v1/packages/a1/p9"
    assert (
        keys.package_object_key(asset_id="a1", package_id="p9", relative_path="master.m3u8")
        == "ifilm/v1/packages/a1/p9/master.m3u8"
    )
    assert (
        keys.artwork_key(
            kind=StorageObjectKind.POSTER,
            asset_id="a1",
            stored_filename="poster.jpg",
        )
        == "ifilm/v1/posters/a1/poster.jpg"
    )


def test_object_key_builder_rejects_traversal():
    keys = ObjectKeyBuilder()
    with pytest.raises(ValueError):
        keys.package_object_key(asset_id="a1", package_id="p9", relative_path="../x")
    with pytest.raises(ValueError):
        keys.original_key(asset_id="../x", stored_filename="a.mp4")


def test_local_storage_roundtrip(tmp_path: Path):
    root = tmp_path / "media"
    store = LocalFilesystemStorage(root=root, role=StorageRole.LOCAL_WORKSPACE)
    src = tmp_path / "src.bin"
    src.write_bytes(b"hello-origin")
    key = "ifilm/v1/originals/a1/a1.bin"
    put = store.put_file(key=key, source=src, content_type="application/octet-stream")
    assert put.size_bytes == 12
    assert store.exists(key=key)
    dest = tmp_path / "out.bin"
    got = store.get_file(key=key, destination=dest)
    assert dest.read_bytes() == b"hello-origin"
    assert got.size_bytes == 12
    health = store.healthcheck()
    assert health["ok"] is True
    assert health["provider"] == "local"


def test_local_storage_rejects_path_escape(tmp_path: Path):
    store = LocalFilesystemStorage(root=tmp_path / "media")
    with pytest.raises(ValueError):
        store.exists(key="../escape.bin")


def test_factory_defaults_to_local(tmp_path: Path):
    settings = Settings(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        media_root=str(tmp_path / "media"),
        enable_object_storage=False,
    )
    local = get_local_workspace_storage(settings)
    origin = get_central_origin_storage(settings)
    assert local.provider_kind == StorageProviderKind.LOCAL
    assert origin.provider_kind == StorageProviderKind.LOCAL
    assert get_hot_tier_storage(settings) is None


def test_safe_storage_status_never_includes_secrets():
    settings = Settings(
        app_env="development",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        enable_object_storage=True,
        media_origin_provider="s3_compatible",
        media_origin_endpoint_url="https://minio.internal:9000",
        media_origin_bucket="ifilm-origin",
        media_origin_access_key_id="AKIA_TEST_KEY",
        media_origin_secret_access_key="super-secret-value-do-not-leak",
        enable_r2_hot_tier=True,
        r2_endpoint_url="https://abc123.r2.cloudflarestorage.com",
        r2_bucket="ifilm-hot",
        r2_access_key_id="R2KEY",
        r2_secret_access_key="r2-secret-should-not-appear",
        cdn_hot_tier_max_titles=25,
    )
    status = safe_storage_status(settings)
    blob = str(status)
    assert "super-secret-value-do-not-leak" not in blob
    assert "r2-secret-should-not-appear" not in blob
    assert "AKIA_TEST_KEY" not in blob
    assert "R2KEY" not in blob
    assert status["roles"]["central_origin"]["endpoint_host"] == "minio.internal"
    assert status["roles"]["hot_cdn"]["enabled"] is True
    assert status["policy"]["mirror_full_library_to_r2"] is False
    assert status["policy"]["cloudflare_stream_default_delivery"] is False
    assert status["policy"]["permanent_public_movie_urls"] is False


def test_validation_requires_s3_fields_when_enabled():
    settings = Settings(
        app_env="development",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        enable_object_storage=True,
        media_origin_provider="s3_compatible",
    )
    errors = collect_object_storage_errors(settings)
    assert any("MEDIA_ORIGIN_ENDPOINT_URL" in e for e in errors)
    assert any("MEDIA_ORIGIN_BUCKET" in e for e in errors)


def test_validation_r2_requires_positive_max_titles():
    settings = Settings(
        app_env="development",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        enable_object_storage=True,
        media_origin_provider="local",
        enable_r2_hot_tier=True,
        r2_endpoint_url="https://abc.r2.cloudflarestorage.com",
        r2_bucket="hot",
        r2_access_key_id="k",
        r2_secret_access_key="s",
        cdn_hot_tier_max_titles=0,
    )
    errors = collect_object_storage_errors(settings)
    assert any("CDN_HOT_TIER_MAX_TITLES" in e for e in errors)


def test_prod_rejects_legacy_cdn_sync():
    settings = Settings(
        app_env="production",
        database_url="postgresql+psycopg2://app:long-enough-password@db:5432/ifilm",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        enable_cdn_sync=True,
        debug=False,
    )
    errors = collect_runtime_errors(settings)
    assert any("ENABLE_CDN_SYNC" in e for e in errors)


def test_s3_compatible_storage_uses_injected_client(tmp_path: Path):
    client = MagicMock()
    cfg = S3CompatibleConfig(
        endpoint_url="https://minio.internal:9000",
        bucket="origin",
        region="us-east-1",
        access_key_id="key",
        secret_access_key="secret",
        role=StorageRole.CENTRAL_ORIGIN,
        provider_kind=StorageProviderKind.S3_COMPATIBLE,
    )
    with patch("app.services.object_storage.s3_compatible._require_boto3") as require:
        fake_boto3 = MagicMock()
        fake_boto3.client.return_value = client
        require.return_value = (fake_boto3, MagicMock())
        store = S3CompatibleStorage(cfg)
    src = tmp_path / "seg.ts"
    src.write_bytes(b"tsdata")
    store.put_file(key="ifilm/v1/packages/a/p/seg.ts", source=src)
    client.upload_file.assert_called()
    health = store.healthcheck()
    assert health["endpoint_host"] == "minio.internal"
    assert "secret" not in str(health)
