"""Tests for public artwork CDN publish via Cloudflare R2."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app.core.config import Settings
from app.services.object_storage.artwork_cdn import (
    artwork_cdn_sync_enabled,
    publish_artwork_file,
    try_publish_artwork_file,
)
from app.services.object_storage.keys import ObjectKeyBuilder, StorageObjectKind
from app.services.object_storage.status import safe_storage_status
from app.services.object_storage.validation import collect_object_storage_errors
from app.services.tmdb.artwork import store_artwork_bytes


def _settings(**kwargs) -> Settings:
    base = dict(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        artwork_root="/tmp/ifilm-test-artwork-cdn",
    )
    base.update(kwargs)
    return Settings(**base)


def test_artwork_relative_key_and_logo_kind():
    keys = ObjectKeyBuilder(prefix="ifilm")
    assert (
        keys.artwork_relative_key(relative_path="posters/tmdb-poster-1-abcdef123456.jpg")
        == "ifilm/v1/posters/tmdb-poster-1-abcdef123456.jpg"
    )
    assert (
        keys.artwork_key(kind=StorageObjectKind.LOGO, asset_id="a1", stored_filename="logo.png")
        == "ifilm/v1/logos/a1/logo.png"
    )


def test_artwork_cdn_validation_requires_base_with_env_r2():
    settings = _settings(
        enable_artwork_cdn_sync=True,
        r2_endpoint_url="https://abc.r2.cloudflarestorage.com",
        r2_bucket="art",
        r2_access_key_id="k",
        r2_secret_access_key="s",
        artwork_cdn_public_base_url="",
    )
    errors = collect_object_storage_errors(settings)
    assert any("ARTWORK_CDN_PUBLIC_BASE_URL" in e for e in errors)


def test_artwork_cdn_off_by_default():
    settings = _settings()
    assert artwork_cdn_sync_enabled(settings) is False
    assert publish_artwork_file(relative_path="posters/x.jpg", source=Path("/nope"), settings=settings) is None


def test_publish_artwork_file_uploads_and_builds_public_url(tmp_path: Path):
    src = tmp_path / "poster.jpg"
    src.write_bytes(b"\xff\xd8\xff" + b"0" * 32)
    store = MagicMock()
    store.exists.return_value = False
    settings = _settings(
        enable_artwork_cdn_sync=True,
        artwork_cdn_public_base_url="https://cdn.example.com",
        r2_endpoint_url="https://abc.r2.cloudflarestorage.com",
        r2_bucket="art",
        r2_access_key_id="k",
        r2_secret_access_key="s",
    )
    result = publish_artwork_file(
        relative_path="posters/tmdb-poster-9-abcdef123456.jpg",
        source=src,
        settings=settings,
        storage=store,
    )
    assert result is not None
    assert result.object_key == "ifilm/v1/posters/tmdb-poster-9-abcdef123456.jpg"
    assert result.public_url == "https://cdn.example.com/ifilm/v1/posters/tmdb-poster-9-abcdef123456.jpg"
    store.put_file.assert_called_once()


def test_try_publish_returns_none_on_failure(tmp_path: Path):
    src = tmp_path / "poster.jpg"
    src.write_bytes(b"x")
    settings = _settings(
        enable_artwork_cdn_sync=True,
        artwork_cdn_public_base_url="https://cdn.example.com",
        # Missing R2 credentials → factory returns None → publish errors → try returns None
    )
    assert try_publish_artwork_file(relative_path="posters/x.jpg", source=src, settings=settings) is None


def test_store_artwork_bytes_uses_cdn_url_when_enabled(tmp_path: Path, monkeypatch):
    root = tmp_path / "artwork"
    settings = _settings(
        artwork_root=str(root),
        enable_artwork_cdn_sync=True,
        artwork_cdn_public_base_url="https://cdn.example.com",
        r2_endpoint_url="https://abc.r2.cloudflarestorage.com",
        r2_bucket="art",
        r2_access_key_id="k",
        r2_secret_access_key="s",
    )

    def fake_publish(**kwargs):
        return "https://cdn.example.com/ifilm/v1/posters/fake.jpg"

    monkeypatch.setattr(
        "app.services.object_storage.artwork_cdn.try_publish_artwork_file",
        fake_publish,
    )
    # Minimal valid JPEG header for store_artwork_bytes validation
    data = b"\xff\xd8\xff\xd9"
    # store_artwork_bytes also checks pillow/mime — use content_type jpeg and magic bytes
    # Need enough for validation - empty after SOI/EOI may fail dimensions
    # Use a tiny valid approach: monkeypatch _validate_image_bytes
    monkeypatch.setattr(
        "app.services.tmdb.artwork._validate_image_bytes",
        lambda data, content_type: ("jpg", 10, 10),
    )
    stored = store_artwork_bytes(
        settings,
        b"fake-image-bytes",
        kind="poster",
        tmdb_id=42,
        content_type="image/jpeg",
    )
    assert stored.url.startswith("https://cdn.example.com/")
    assert (root / stored.relative_path).is_file()


def test_safe_storage_status_includes_artwork_cdn_without_secrets():
    settings = _settings(
        enable_artwork_cdn_sync=True,
        artwork_cdn_public_base_url="https://cdn.example.com",
        r2_endpoint_url="https://abc.r2.cloudflarestorage.com",
        r2_bucket="art",
        r2_access_key_id="SECRETKEY",
        r2_secret_access_key="super-secret-artwork",
    )
    status = safe_storage_status(settings)
    blob = str(status)
    assert "super-secret-artwork" not in blob
    assert "SECRETKEY" not in blob
    assert status["roles"]["artwork_cdn"]["enabled"] is True
    assert status["roles"]["artwork_cdn"]["movies_remain_local"] is True
    assert status["policy"]["permanent_public_movie_urls"] is False
