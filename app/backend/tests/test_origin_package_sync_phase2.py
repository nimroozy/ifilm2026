"""Phase 2 origin package sync + HLS read-fallback tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.core.config import Settings
from app.models.media_assets import MediaAsset, new_uuid
from app.models.media_encoding import MediaPackage, MediaRendition
from app.models.media_processing import JOB_TYPE_ORIGIN_SYNC
from app.services.object_storage.factory import get_central_origin_storage
from app.services.object_storage.keys import ObjectKeyBuilder
from app.services.object_storage.local import LocalFilesystemStorage
from app.services.object_storage.origin_read import fetch_package_object_bytes
from app.services.object_storage.package_sync import (
    ORIGIN_SYNC_STATUS_SYNCED,
    OriginSyncError,
    enqueue_origin_package_sync,
    execute_origin_sync_job,
    origin_package_sync_enabled,
    sync_package_tree,
)
from app.services.object_storage.status import safe_storage_status
from app.services.object_storage.validation import collect_object_storage_errors
from app.services.streaming.delivery import deliver_master, deliver_segment
from app.services.streaming.paths import StreamPathError
from app.services.streaming.tokens import generate_playback_token, hash_playback_token
from starlette.requests import Request as StarletteRequest


def _settings(**kwargs) -> Settings:
    base = dict(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        enable_object_storage=False,
        enable_origin_package_sync=False,
        enable_origin_hls_read_fallback=False,
        enable_cdn_sync=False,
        media_object_key_prefix="ifilm",
        _env_file=None,
    )
    base.update(kwargs)
    return Settings(**base)


def _make_package_tree(root: Path, *, asset_id: str, package_id: str) -> Path:
    pkg = root / "packages" / asset_id / package_id
    (pkg / "720p").mkdir(parents=True)
    (pkg / "master.m3u8").write_text(
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\n720p/index.m3u8\n",
        encoding="utf-8",
    )
    (pkg / "720p" / "index.m3u8").write_text(
        "#EXTM3U\n#EXTINF:6.0,\nseg_000.ts\n#EXT-X-ENDLIST\n",
        encoding="utf-8",
    )
    (pkg / "720p" / "seg_000.ts").write_bytes(b"\x00" * 64)
    return pkg


def test_origin_sync_flag_defaults_off():
    settings = _settings()
    assert origin_package_sync_enabled(settings) is False
    assert settings.enable_origin_package_sync is False
    assert settings.enable_origin_hls_read_fallback is False


def test_validation_origin_sync_requires_object_storage():
    settings = _settings(enable_origin_package_sync=True, enable_object_storage=False)
    errors = collect_object_storage_errors(settings)
    assert any("ENABLE_ORIGIN_PACKAGE_SYNC" in e for e in errors)


def test_sync_package_tree_idempotent(tmp_path: Path):
    media = tmp_path / "media"
    asset_id = "asset-1"
    package_id = "pkg-1"
    _make_package_tree(media, asset_id=asset_id, package_id=package_id)
    package = MediaPackage(
        id=package_id,
        media_asset_id=asset_id,
        status="completed",
        is_active=True,
        storage_path=f"packages/{asset_id}/{package_id}",
        master_playlist_path=f"packages/{asset_id}/{package_id}/master.m3u8",
    )
    settings = _settings(
        media_root=str(media),
        enable_object_storage=True,
        media_origin_provider="local",
        enable_origin_package_sync=True,
    )
    # Origin uses a separate local root via factory → same MEDIA_ROOT when provider=local.
    storage = LocalFilesystemStorage(root=media)
    first = sync_package_tree(package=package, storage=storage, settings=settings)
    assert first.object_count >= 3
    assert first.bytes_synced > 0
    second = sync_package_tree(package=package, storage=storage, settings=settings)
    assert second.skipped_existing >= 3
    key = ObjectKeyBuilder().package_object_key(
        asset_id=asset_id, package_id=package_id, relative_path="master.m3u8"
    )
    assert storage.exists(key=key)
    # Local original untouched.
    assert (media / "packages" / asset_id / package_id / "master.m3u8").is_file()


def test_sync_rejects_size_mismatch(tmp_path: Path):
    media = tmp_path / "media"
    asset_id = "asset-2"
    package_id = "pkg-2"
    _make_package_tree(media, asset_id=asset_id, package_id=package_id)
    package = MediaPackage(
        id=package_id,
        media_asset_id=asset_id,
        status="completed",
        is_active=True,
        storage_path=f"packages/{asset_id}/{package_id}",
    )
    settings = _settings(media_root=str(media), media_object_key_prefix="ifilm")
    storage = MagicMock()
    storage.exists.return_value = False
    storage.put_file.return_value = MagicMock(size_bytes=1, key="x")  # wrong size
    with pytest.raises(OriginSyncError) as exc:
        sync_package_tree(package=package, storage=storage, settings=settings)
    assert exc.value.code == "size_mismatch"


def test_enqueue_noop_when_flags_off(db_session, tmp_path: Path):
    asset = MediaAsset(
        id=new_uuid(),
        original_filename="a.mp4",
        stored_filename="a.mp4",
        category="originals",
        mime_type="video/mp4",
        size_bytes=10,
        checksum_sha256="a" * 64,
        storage_backend="local",
        storage_path="originals/x/a.mp4",
        upload_status="completed",
    )
    package = MediaPackage(
        id=new_uuid(),
        media_asset_id=asset.id,
        status="completed",
        is_active=True,
        storage_path="packages/x/y",
    )
    db_session.add(asset)
    db_session.add(package)
    db_session.commit()
    settings = _settings(enable_object_storage=False, enable_origin_package_sync=False)
    assert enqueue_origin_package_sync(db_session, package=package, settings=settings) is None


def test_enqueue_and_execute_origin_sync_job(db_session, tmp_path: Path, monkeypatch):
    media = tmp_path / "media"
    asset_id = new_uuid()
    package_id = new_uuid()
    _make_package_tree(media, asset_id=asset_id, package_id=package_id)

    asset = MediaAsset(
        id=asset_id,
        original_filename="a.mp4",
        stored_filename="a.mp4",
        category="originals",
        mime_type="video/mp4",
        size_bytes=10,
        checksum_sha256="b" * 64,
        storage_backend="local",
        storage_path=f"originals/{asset_id}/a.mp4",
        upload_status="completed",
    )
    package = MediaPackage(
        id=package_id,
        media_asset_id=asset_id,
        status="completed",
        is_active=True,
        storage_path=f"packages/{asset_id}/{package_id}",
        master_playlist_path=f"packages/{asset_id}/{package_id}/master.m3u8",
    )
    db_session.add(asset)
    db_session.add(package)
    db_session.commit()

    settings = _settings(
        media_root=str(media),
        enable_object_storage=True,
        media_origin_provider="local",
        enable_origin_package_sync=True,
    )
    job = enqueue_origin_package_sync(db_session, package=package, settings=settings)
    assert job is not None
    assert job.job_type == JOB_TYPE_ORIGIN_SYNC
    assert job.target_package_id == package_id
    db_session.refresh(package)
    assert package.origin_sync_status == "pending"

    execute_origin_sync_job(db_session, job, settings=settings)
    db_session.refresh(package)
    db_session.refresh(job)
    assert job.status == "completed"
    assert package.origin_sync_status == ORIGIN_SYNC_STATUS_SYNCED
    assert package.is_active is True
    assert package.origin_object_prefix
    status = safe_storage_status(settings)
    assert "secret" not in str(status).lower() or "secret_access" not in str(status)


def test_origin_read_fallback_requires_synced_and_confinement(tmp_path: Path):
    media = tmp_path / "media"
    asset_id = "asset-r"
    package_id = "pkg-r"
    _make_package_tree(media, asset_id=asset_id, package_id=package_id)
    settings = _settings(
        media_root=str(media),
        enable_object_storage=True,
        media_origin_provider="local",
        enable_origin_hls_read_fallback=True,
        media_object_key_prefix="ifilm",
    )
    storage = get_central_origin_storage(settings)
    package = MediaPackage(
        id=package_id,
        media_asset_id=asset_id,
        status="completed",
        is_active=True,
        storage_path=f"packages/{asset_id}/{package_id}",
        origin_sync_status=ORIGIN_SYNC_STATUS_SYNCED,
        origin_object_prefix=f"ifilm/v1/packages/{asset_id}/{package_id}",
    )
    package.renditions = [MediaRendition(id=new_uuid(), package_id=package_id, label="720p", height=720)]
    # Sync into origin key layout under same media root.
    sync_package_tree(package=package, storage=storage, settings=settings)
    data = fetch_package_object_bytes(package, "master.m3u8", settings=settings)
    assert b"#EXTM3U" in data
    with pytest.raises(StreamPathError):
        fetch_package_object_bytes(package, "../escape.m3u8", settings=settings)
    with pytest.raises(StreamPathError):
        fetch_package_object_bytes(package, "evil/index.m3u8", settings=settings)


def test_delivery_local_first_when_fallback_off(db_session, tmp_path: Path, monkeypatch):
    from datetime import timedelta

    import app.services.storage as storage_mod
    from app.core.config import get_settings
    from app.models.media_assets import utcnow
    from app.models.media_playback import MediaPlaybackSession

    media = tmp_path / "media"
    asset_id = new_uuid()
    package_id = new_uuid()
    _make_package_tree(media, asset_id=asset_id, package_id=package_id)
    monkeypatch.setenv("MEDIA_ROOT", str(media))
    get_settings.cache_clear()
    monkeypatch.setattr(storage_mod, "media_root", lambda: media.resolve())
    monkeypatch.setattr(
        storage_mod,
        "packages_dir",
        lambda create=True: (media / "packages"),
    )

    asset = MediaAsset(
        id=asset_id,
        original_filename="a.mp4",
        stored_filename="a.mp4",
        category="originals",
        mime_type="video/mp4",
        size_bytes=10,
        checksum_sha256="c" * 64,
        storage_backend="local",
        storage_path=f"originals/{asset_id}/a.mp4",
        upload_status="completed",
    )
    package = MediaPackage(
        id=package_id,
        media_asset_id=asset_id,
        status="completed",
        is_active=True,
        storage_path=f"packages/{asset_id}/{package_id}",
        master_playlist_path=f"packages/{asset_id}/{package_id}/master.m3u8",
        origin_sync_status="none",
    )
    rendition = MediaRendition(
        id=new_uuid(), package_id=package_id, label="720p", height=720, status="completed"
    )
    raw = generate_playback_token()
    session = MediaPlaybackSession(
        id=new_uuid(),
        token_hash=hash_playback_token(raw),
        media_asset_id=asset_id,
        media_package_id=package_id,
        principal_type="admin",
        principal_id="1",
        status="active",
        expires_at=utcnow() + timedelta(hours=1),
    )
    db_session.add_all([asset, package, rendition, session])
    db_session.commit()
    db_session.refresh(session)
    session.media_package = package
    package.renditions = [rendition]

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    request = StarletteRequest(scope)
    resp = deliver_master(db_session, raw, request)
    assert resp.status_code == 200
    assert "application/vnd.apple.mpegurl" in (resp.media_type or "")
    assert f"/api/stream/{raw}/720p/index.m3u8" in resp.body.decode()

    seg = deliver_segment(db_session, raw, "720p", "seg_000.ts", request)
    assert seg.status_code == 200
    assert seg.media_type == "video/mp2t"
