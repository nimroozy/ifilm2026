"""Media upload foundation API tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.services.storage import ensure_media_layout, media_root


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_admin(db_session, *, username: str, permissions: list[str]) -> str:
    role = AdminRole(name=f"role-{username}", permissions=permissions)
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username=username,
        email=f"{username}@example.test",
        full_name=username,
        hashed_password=hash_password("upload-admin-pass-ok"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})


def _create_session(client, headers, *, filename="clip.mp4", size=11, mime="video/mp4", **extra):
    payload = {
        "filename": filename,
        "mime_type": mime,
        "size_bytes": size,
        "category": "originals",
        **extra,
    }
    return client.post("/api/admin/media/sessions", headers=headers, json=payload)


def test_media_upload_requires_auth(client):
    assert client.post("/api/admin/media/sessions", json={}).status_code == 401
    assert client.get("/api/admin/media/assets").status_code == 401


def test_media_upload_rbac(client, db_session):
    reader = _make_admin(db_session, username="upload-reader", permissions=["upload.read"])
    manager = _make_admin(db_session, username="upload-manager", permissions=["upload.manage"])
    movies_only = _make_admin(db_session, username="movies-only", permissions=["movies.manage"])

    assert client.get("/api/admin/media/assets", headers=_headers(reader)).status_code == 200
    assert (
        client.post(
            "/api/admin/media/sessions",
            headers=_headers(reader),
            json={"filename": "a.mp4", "mime_type": "video/mp4", "size_bytes": 10},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/admin/media/sessions",
            headers=_headers(movies_only),
            json={"filename": "a.mp4", "mime_type": "video/mp4", "size_bytes": 10},
        ).status_code
        == 403
    )
    created = _create_session(client, _headers(manager), size=10)
    assert created.status_code == 201, created.text


def test_reject_zero_byte_and_oversized(client, admin_headers, monkeypatch):
    zero = _create_session(client, admin_headers, size=0)
    assert zero.status_code == 422

    monkeypatch.setenv("UPLOAD_MAX_BYTES", "100")
    get_settings.cache_clear()
    oversized = _create_session(client, admin_headers, size=101)
    assert oversized.status_code == 400
    assert oversized.json()["detail"] == "File too large"
    monkeypatch.delenv("UPLOAD_MAX_BYTES", raising=False)
    get_settings.cache_clear()


def test_reject_unsupported_type_path_traversal_and_executable(client, admin_headers):
    bad_mime = _create_session(client, admin_headers, mime="text/plain")
    assert bad_mime.status_code == 400

    traversal = _create_session(client, admin_headers, filename="../etc/passwd")
    assert traversal.status_code == 400

    exe = _create_session(client, admin_headers, filename="payload.exe", mime="application/octet-stream")
    assert exe.status_code == 400
    assert "Executable" in exe.json()["detail"]


def test_reject_multiple_owners(client, admin_headers):
    response = client.post(
        "/api/admin/media/sessions",
        headers=admin_headers,
        json={
            "filename": "clip.mp4",
            "mime_type": "video/mp4",
            "size_bytes": 10,
            "movie_id": 1,
            "series_id": 2,
        },
    )
    assert response.status_code == 422


def test_streaming_upload_checksum_and_storage_path(client, admin_headers):
    payload = b"hello-media"
    created = _create_session(client, admin_headers, size=len(payload))
    assert created.status_code == 201, created.text
    session_id = created.json()["session"]["id"]
    asset_id = created.json()["media_asset"]["id"]

    progress = client.get(f"/api/admin/media/sessions/{session_id}", headers=admin_headers)
    assert progress.status_code == 200
    assert progress.json()["status"] == "pending"

    uploaded = client.put(
        f"/api/admin/media/sessions/{session_id}",
        headers=admin_headers,
        files={"file": ("clip.mp4", payload, "video/mp4")},
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["status"] == "completed"
    assert body["progress_percent"] == 100
    assert body["bytes_received"] == len(payload)

    asset = client.get(f"/api/admin/media/assets/{asset_id}", headers=admin_headers)
    assert asset.status_code == 200
    meta = asset.json()
    assert meta["checksum_sha256"] == hashlib.sha256(payload).hexdigest()
    assert meta["upload_status"] == "completed"
    assert meta["storage_backend"] == "local"
    assert meta["storage_path"]
    assert meta["storage_path"].startswith("originals/")
    stored = media_root() / meta["storage_path"]
    assert stored.exists()
    assert stored.read_bytes() == payload


def test_duplicate_checksum_rejected(client, admin_headers, monkeypatch):
    monkeypatch.setenv("UPLOAD_REJECT_DUPLICATE_CHECKSUM", "true")
    get_settings.cache_clear()
    payload = b"duplicate-bytes"
    first = _create_session(client, admin_headers, filename="one.mp4", size=len(payload))
    assert (
        client.put(
            f"/api/admin/media/sessions/{first.json()['session']['id']}",
            headers=admin_headers,
            files={"file": ("one.mp4", payload, "video/mp4")},
        ).status_code
        == 200
    )

    second = _create_session(client, admin_headers, filename="two.mp4", size=len(payload))
    dup = client.put(
        f"/api/admin/media/sessions/{second.json()['session']['id']}",
        headers=admin_headers,
        files={"file": ("two.mp4", payload, "video/mp4")},
    )
    assert dup.status_code == 409
    assert "Duplicate" in dup.json()["detail"]
    monkeypatch.delenv("UPLOAD_REJECT_DUPLICATE_CHECKSUM", raising=False)
    get_settings.cache_clear()


def test_cancel_upload_session(client, admin_headers):
    created = _create_session(client, admin_headers, size=20)
    session_id = created.json()["session"]["id"]
    cancelled = client.delete(f"/api/admin/media/sessions/{session_id}", headers=admin_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    put = client.put(
        f"/api/admin/media/sessions/{session_id}",
        headers=admin_headers,
        files={"file": ("clip.mp4", b"12345678901234567890", "video/mp4")},
    )
    assert put.status_code == 409


def test_large_file_streaming(client, admin_headers):
    # ~1.5 MiB streamed in chunks by the service.
    payload = (b"abcdefghij" * 1024) * 150  # 1,536,000 bytes
    created = _create_session(client, admin_headers, filename="large.mp4", size=len(payload))
    assert created.status_code == 201
    session_id = created.json()["session"]["id"]
    uploaded = client.put(
        f"/api/admin/media/sessions/{session_id}",
        headers=admin_headers,
        files={"file": ("large.mp4", payload, "video/mp4")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["bytes_received"] == len(payload)
    asset_id = created.json()["media_asset"]["id"]
    meta = client.get(f"/api/admin/media/assets/{asset_id}", headers=admin_headers).json()
    assert meta["checksum_sha256"] == hashlib.sha256(payload).hexdigest()


def test_storage_layout_and_path_generation():
    root = ensure_media_layout()
    for name in ("originals", "posters", "backdrops", "trailers", "subtitles", "temp"):
        assert (root / name).is_dir()
    assert root == media_root()
    assert Path(root).is_absolute()


def test_list_media_assets(client, admin_headers):
    payload = b"list-me"
    created = _create_session(client, admin_headers, filename="listed.mp4", size=len(payload))
    client.put(
        f"/api/admin/media/sessions/{created.json()['session']['id']}",
        headers=admin_headers,
        files={"file": ("listed.mp4", payload, "video/mp4")},
    )
    listed = client.get("/api/admin/media/assets", headers=admin_headers)
    assert listed.status_code == 200
    body = listed.json()
    assert "data" in body
    assert any(item["original_filename"] == "listed.mp4" for item in body["data"])
