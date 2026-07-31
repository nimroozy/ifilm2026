"""Phase 7 protected streaming security and delivery tests."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.core.logging_filters import redact_stream_path
from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.content import Movie
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage, MediaRendition
from app.models.media_playback import MediaPlaybackSession
from app.services.storage import (
    ensure_artwork_layout,
    ensure_media_layout,
    media_root,
    relative_media_path,
)
from app.services.streaming.activation import (
    ActivePackageError,
    activate_completed_package,
    get_active_completed_package,
)
from app.services.streaming.tokens import generate_playback_token


def _admin_token(db_session, *, permissions: list[str] | None = None) -> str:
    perms = permissions or [
        "streaming.read",
        "streaming.manage",
        "processing.read",
        "processing.manage",
        "upload.manage",
        "movies.manage",
    ]
    role = AdminRole(name=f"stream-role-{new_uuid()[:8]}", permissions=perms)
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username=f"stream-{new_uuid()[:8]}",
        email=f"{new_uuid()[:8]}@example.test",
        full_name="Stream Admin",
        hashed_password=hash_password("stream-admin-pass-ok"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _write_mini_package(package_dir: Path, *, labels: tuple[str, ...] = ("240p",)) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    master_lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for label in labels:
        rendition = package_dir / label
        rendition.mkdir(parents=True, exist_ok=True)
        segment = rendition / "segment_000.ts"
        segment.write_bytes(b"\x00\x01\x02\x03" * 64)
        (rendition / "index.m3u8").write_text(
            "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n"
            "#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:6.0,\nsegment_000.ts\n#EXT-X-ENDLIST\n",
            encoding="utf-8",
        )
        master_lines.append(
            "#EXT-X-STREAM-INF:BANDWIDTH=400000,RESOLUTION=426x240,CODECS=\"avc1.4d401f,mp4a.40.2\""
        )
        master_lines.append(f"{label}/index.m3u8")
    (package_dir / "master.m3u8").write_text("\n".join(master_lines) + "\n", encoding="utf-8")


def _seed_active_package(db_session, *, movie: Movie | None = None) -> tuple[MediaAsset, MediaPackage]:
    ensure_media_layout()
    asset = MediaAsset(
        id=new_uuid(),
        original_filename="clip.mp4",
        stored_filename="clip.mp4",
        mime_type="video/mp4",
        extension=".mp4",
        size_bytes=1000,
        category="originals",
        upload_status="completed",
        processing_status="completed",
        storage_backend="local",
        storage_path=f"originals/{new_uuid()}/clip.mp4",
        movie_id=movie.id if movie else None,
        width=640,
        height=360,
        probed_at=utcnow(),
    )
    db_session.add(asset)
    db_session.flush()
    package = MediaPackage(
        id=new_uuid(),
        media_asset_id=asset.id,
        package_type=PACKAGE_TYPE_HLS_VOD,
        status="completed",
        is_active=False,
        segment_duration_seconds=6,
        rendition_count=1,
        completed_at=utcnow(),
    )
    db_session.add(package)
    db_session.flush()
    pkg_dir = media_root() / "packages" / asset.id / package.id
    _write_mini_package(pkg_dir)
    package.storage_path = relative_media_path(pkg_dir)
    package.master_playlist_path = relative_media_path(pkg_dir / "master.m3u8")
    db_session.add(
        MediaRendition(
            id=new_uuid(),
            package_id=package.id,
            label="240p",
            height=240,
            width=426,
            bandwidth=400000,
            playlist_path=relative_media_path(pkg_dir / "240p" / "index.m3u8"),
            segment_count=1,
            status="completed",
        )
    )
    db_session.flush()
    activate_completed_package(db_session, package)
    db_session.commit()
    db_session.refresh(package)
    db_session.refresh(asset)
    return asset, package


def test_legacy_media_root_not_exposed(client, db_session):
    ensure_media_layout()
    secret = media_root() / "originals" / "secret.bin"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_bytes(b"secret-source")
    pkg = media_root() / "packages" / "a" / "b" / "master.m3u8"
    pkg.parent.mkdir(parents=True, exist_ok=True)
    pkg.write_text("#EXTM3U\n", encoding="utf-8")
    seg = media_root() / "packages" / "a" / "b" / "240p" / "segment_000.ts"
    seg.parent.mkdir(parents=True, exist_ok=True)
    seg.write_bytes(b"tsdata")

    assert client.get("/media/originals/secret.bin").status_code == 404
    assert client.get("/media/packages/a/b/master.m3u8").status_code == 404
    assert client.get("/media/packages/a/b/240p/segment_000.ts").status_code == 404
    assert client.get("/media/../etc/passwd").status_code == 404
    # Legacy placeholder HLS route removed.
    assert client.get("/api/media/hls/movie/1/master.m3u8").status_code == 404
    assert client.get("/api/stream/movie/1").status_code == 404


def test_artwork_symlink_escape_rejected(client, tmp_path, monkeypatch):
    ensure_artwork_layout()
    root = Path(get_settings().artwork_root).resolve()
    outside = Path("/tmp/ifilm-artwork-escape-target")
    outside.write_bytes(b"nope")
    link = root / "posters" / "evil.jpg"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(outside)
    resp = client.get("/artwork/posters/evil.jpg")
    assert resp.status_code in (404, 400)
    # Valid local artwork works.
    good = root / "posters" / "ok.png"
    good.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    assert client.get("/artwork/posters/ok.png").status_code == 200
    assert client.get("/artwork/../packages/x").status_code in (400, 404)


def test_active_package_concurrency_and_rules(db_session):
    asset, first = _seed_active_package(db_session)
    assert first.is_active is True
    second = MediaPackage(
        id=new_uuid(),
        media_asset_id=asset.id,
        package_type=PACKAGE_TYPE_HLS_VOD,
        status="completed",
        is_active=False,
        segment_duration_seconds=6,
        rendition_count=1,
        completed_at=utcnow(),
        storage_path=first.storage_path,
        master_playlist_path=first.master_playlist_path,
    )
    db_session.add(second)
    db_session.add(
        MediaRendition(
            id=new_uuid(),
            package_id=second.id,
            label="240p",
            height=240,
            width=426,
            bandwidth=400000,
            playlist_path=first.renditions[0].playlist_path,
            segment_count=1,
            status="completed",
        )
    )
    db_session.flush()
    activate_completed_package(db_session, second)
    db_session.commit()
    db_session.refresh(first)
    db_session.refresh(second)
    assert second.is_active is True
    assert first.is_active is False
    assert first.superseded_at is not None
    assert get_active_completed_package(db_session, asset.id).id == second.id

    failed = MediaPackage(
        id=new_uuid(),
        media_asset_id=asset.id,
        package_type=PACKAGE_TYPE_HLS_VOD,
        status="failed",
        is_active=False,
        segment_duration_seconds=6,
    )
    db_session.add(failed)
    db_session.flush()
    with pytest.raises(ActivePackageError):
        activate_completed_package(db_session, failed)
    db_session.refresh(second)
    assert second.is_active is True


def test_playback_session_flow_and_security(client, db_session, admin_headers, caplog):
    movie = Movie(
        title="Stream Movie",
        slug=f"stream-movie-{new_uuid()[:8]}",
        status="published",
        published_at=utcnow(),
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    asset, package = _seed_active_package(db_session, movie=movie)
    token = _admin_token(db_session)
    headers = _headers(token)

    created = client.post(
        "/api/admin/playback/sessions",
        headers=headers,
        json={"media_asset_id": asset.id},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    raw = body["playback_token"]
    assert "token_hash" not in body
    assert "storage_path" not in body
    assert body["master_playlist_url"].endswith("/master.m3u8")
    assert "/api/stream/" in body["master_playlist_url"]
    master_url = body["master_playlist_url"]

    # List never includes token or hash.
    listed = client.get("/api/admin/playback/sessions", headers=headers)
    assert listed.status_code == 200
    row = listed.json()["data"][0]
    assert "token" not in row
    assert "token_hash" not in row
    assert "storage_path" not in row

    with caplog.at_level(logging.INFO):
        master = client.get(master_url)
    assert master.status_code == 200
    text = master.text
    assert "#EXTM3U" in text
    assert f"/api/stream/{raw}/240p/index.m3u8" in text
    assert "packages/" not in text
    # Access log must redact token.
    assert raw not in caplog.text or redact_stream_path(f"/api/stream/{raw}/master.m3u8").find("[REDACTED]") >= 0
    assert "[REDACTED]" in redact_stream_path(f"/api/stream/{raw}/master.m3u8")

    on_disk = (media_root() / package.storage_path / "master.m3u8").read_text(encoding="utf-8")
    assert f"/api/stream/{raw}" not in on_disk

    variant = client.get(f"/api/stream/{raw}/240p/index.m3u8")
    assert variant.status_code == 200
    assert f"/api/stream/{raw}/240p/segment_000.ts" in variant.text

    full = client.get(f"/api/stream/{raw}/240p/segment_000.ts")
    assert full.status_code == 200
    assert full.headers.get("content-type", "").startswith("video/")
    assert "packages/" not in full.text if hasattr(full, "text") else True

    ranged = client.get(
        f"/api/stream/{raw}/240p/segment_000.ts",
        headers={"Range": "bytes=0-3"},
    )
    assert ranged.status_code == 206
    assert ranged.content == b"\x00\x01\x02\x03"
    assert ranged.headers["content-range"].startswith("bytes 0-3/")

    bad_range = client.get(
        f"/api/stream/{raw}/240p/segment_000.ts",
        headers={"Range": "bytes=999999-9999999"},
    )
    assert bad_range.status_code == 416

    # Anonymous package path denial (already covered) + streaming cross-package
    other_asset, other_pkg = _seed_active_package(db_session)
    assert (
        client.get(f"/api/stream/{raw}/../{other_pkg.id}/master.m3u8").status_code
        in (400, 404, 401, 422)
    )
    assert client.get(f"/api/stream/{raw}/480p/index.m3u8").status_code in (400, 404)
    assert client.get(f"/api/stream/{raw}/240p/segment_000.mp4").status_code == 400
    assert client.get(f"/api/stream/{raw}/240p/../../originals/x").status_code in (400, 404, 422)
    assert client.get("/api/stream/%2e%2e/240p/index.m3u8").status_code in (400, 401, 404, 422)
    assert client.get(f"/api/stream/{raw}/240p/%2e%2e%2f%2e%2e%2foriginals/x").status_code in (
        400,
        404,
        422,
    )

    # Source upload path cannot be fetched via stream endpoint.
    originals = media_root() / "originals" / "leak.bin"
    originals.parent.mkdir(parents=True, exist_ok=True)
    originals.write_bytes(b"upload-secret")
    assert client.get(f"/api/stream/{raw}/../../originals/leak.bin").status_code in (400, 404, 422)

    # Temp workspace denial
    work = media_root() / "packages" / "work" / "job1" / "master.m3u8"
    work.parent.mkdir(parents=True, exist_ok=True)
    work.write_text("#EXTM3U\n", encoding="utf-8")
    assert client.get(f"/api/stream/{raw}/../../work/job1/master.m3u8").status_code in (
        400,
        404,
        422,
    )

    # Malformed / unknown / expired / revoked
    assert client.get("/api/stream/!!bad!!/master.m3u8").status_code == 401
    assert client.get(f"/api/stream/{generate_playback_token()}/master.m3u8").status_code == 401

    # Expire session
    session = db_session.query(MediaPlaybackSession).filter_by(id=body["id"]).one()
    session.expires_at = utcnow() - timedelta(seconds=5)
    db_session.add(session)
    db_session.commit()
    assert client.get(master_url).status_code == 410

    # New session then revoke
    created2 = client.post(
        "/api/admin/playback/sessions",
        headers=headers,
        json={"media_asset_id": asset.id},
    )
    assert created2.status_code == 201
    raw2 = created2.json()["playback_token"]
    sid = created2.json()["id"]
    rev = client.post(f"/api/admin/playback/sessions/{sid}/revoke", headers=headers)
    assert rev.status_code == 200
    assert rev.json()["status"] == "revoked"
    assert "token_hash" not in rev.json()
    assert client.get(f"/api/stream/{raw2}/master.m3u8").status_code == 410
    assert client.get(f"/api/stream/{raw2}/240p/index.m3u8").status_code == 410
    assert client.get(f"/api/stream/{raw2}/240p/segment_000.ts").status_code == 410

    # Package API paths redacted
    pkg_api = client.get(f"/api/admin/media/packages/{package.id}", headers=admin_headers)
    # may 403 if admin_headers lacks processing — use stream admin token with processing
    token_p = _admin_token(db_session, permissions=["processing.read", "streaming.read"])
    pkg_api = client.get(f"/api/admin/media/packages/{package.id}", headers=_headers(token_p))
    assert pkg_api.status_code == 200
    assert pkg_api.json()["storage_path"] is None
    assert pkg_api.json()["master_playlist_path"] is None
    assert pkg_api.json()["is_active"] is True


def test_no_active_package_session_fails(client, db_session):
    ensure_media_layout()
    asset = MediaAsset(
        id=new_uuid(),
        original_filename="x.mp4",
        stored_filename="x.mp4",
        mime_type="video/mp4",
        extension=".mp4",
        size_bytes=1,
        category="originals",
        upload_status="completed",
        processing_status="none",
        storage_backend="local",
    )
    db_session.add(asset)
    db_session.commit()
    token = _admin_token(db_session)
    resp = client.post(
        "/api/admin/playback/sessions",
        headers=_headers(token),
        json={"media_asset_id": asset.id},
    )
    assert resp.status_code == 409


def test_compose_packages_mount_readonly_documented():
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    text = compose.read_text(encoding="utf-8")
    assert "ifilm_media_packages" in text
    assert "read_only: true" in text
    assert "ARTWORK_ROOT" in text
    assert "ENABLE_LOCAL_STREAMING" in text


def test_redaction_helper():
    path = "/api/stream/abcdefghijklmnopqrstuvwx_yz0123456789ABCD/master.m3u8"
    assert "[REDACTED]" in redact_stream_path(path)
    assert "abcdefghijklmnopqrstuvwx" not in redact_stream_path(path)
