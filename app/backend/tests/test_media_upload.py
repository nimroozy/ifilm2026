"""Media upload foundation API tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.services.storage import ensure_media_layout, media_root


def _headers(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def _put_headers(admin_headers: dict[str, str], *, offset: int, complete: bool) -> dict[str, str]:
    return {
        **admin_headers,
        "Upload-Offset": str(offset),
        "Upload-Complete": "true" if complete else "false",
    }


def minimal_mp4(extra: bytes = b"") -> bytes:
    """Minimal ISO BMFF buffer with an ``ftyp`` box (enough for signature checks)."""
    payload = b"isom" + b"\x00\x00\x00\x00" + b"isomiso2mp41"
    box = (8 + len(payload)).to_bytes(4, "big") + b"ftyp" + payload
    return box + extra


def minimal_jpeg(extra: bytes = b"") -> bytes:
    return b"\xff\xd8\xff\xe0\x00\x10JFIF" + extra + b"\xff\xd9"


def minimal_png(extra: bytes = b"") -> bytes:
    return b"\x89PNG\r\n\x1a\n" + extra


def pe_executable() -> bytes:
    return b"MZ" + b"\x00" * 60 + b"PE\x00\x00fake"


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


def _put(
    client,
    admin_headers,
    session_id: str,
    payload: bytes,
    *,
    offset: int,
    complete: bool,
    filename="clip.mp4",
    mime="video/mp4",
):
    return client.put(
        f"/api/admin/media/sessions/{session_id}",
        headers=_put_headers(admin_headers, offset=offset, complete=complete),
        files={"file": (filename, payload, mime)},
    )


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
    bad_mime = _create_session(client, admin_headers, mime="text/html")
    assert bad_mime.status_code == 400

    traversal = _create_session(client, admin_headers, filename="../etc/passwd")
    assert traversal.status_code == 400

    exe = _create_session(
        client, admin_headers, filename="payload.exe", mime="application/octet-stream"
    )
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


def test_size_equality_short_exact_and_over(client, admin_headers):
    base = minimal_mp4()
    # Pad to exactly 10 / build variants.
    exact = (base + b"\x00" * 64)[:10]
    assert len(exact) == 10
    # Ensure ftyp still present
    assert exact[4:8] == b"ftyp"

    short = exact[:5]
    over = exact + b"X"

    # declared 10, received 5 with Upload-Complete → failed, not completed
    created = _create_session(client, admin_headers, size=10)
    session_id = created.json()["session"]["id"]
    asset_id = created.json()["media_asset"]["id"]
    resp = _put(client, admin_headers, session_id, short, offset=0, complete=True)
    assert resp.status_code == 400
    assert "Incomplete upload" in resp.json()["detail"]
    progress = client.get(f"/api/admin/media/sessions/{session_id}", headers=admin_headers).json()
    assert progress["status"] == "failed"
    asset = client.get(f"/api/admin/media/assets/{asset_id}", headers=admin_headers).json()
    assert asset["upload_status"] == "failed"
    assert asset["checksum_sha256"] is None
    assert asset["storage_path"] is None

    # declared 10, received 10 → completed
    created = _create_session(client, admin_headers, filename="ok.mp4", size=10)
    session_id = created.json()["session"]["id"]
    resp = _put(client, admin_headers, session_id, exact, offset=0, complete=True)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "completed"

    # declared 10, received 11 → rejected
    created = _create_session(client, admin_headers, filename="over.mp4", size=10)
    session_id = created.json()["session"]["id"]
    resp = _put(client, admin_headers, session_id, over, offset=0, complete=True)
    assert resp.status_code == 400
    assert "exceeds" in resp.json()["detail"].lower()


def test_interrupted_short_upload_never_completed(client, admin_headers):
    payload = minimal_mp4(b"\x00" * 20)
    created = _create_session(client, admin_headers, size=len(payload))
    session_id = created.json()["session"]["id"]
    # Client stops early without Upload-Complete → stays uploading (not completed)
    partial = payload[:8]
    resp = _put(client, admin_headers, session_id, partial, offset=0, complete=False)
    assert resp.status_code == 200
    assert resp.json()["status"] == "uploading"
    assert resp.json()["bytes_received"] == 8
    asset = client.get(
        f"/api/admin/media/assets/{created.json()['media_asset']['id']}", headers=admin_headers
    ).json()
    assert asset["upload_status"] == "uploading"
    assert asset["checksum_sha256"] is None


def test_resumable_chunks_and_wrong_offset(client, admin_headers):
    payload = minimal_mp4(b"\x00" * 40)
    mid = 16
    created = _create_session(client, admin_headers, size=len(payload))
    session_id = created.json()["session"]["id"]

    first = _put(client, admin_headers, session_id, payload[:mid], offset=0, complete=False)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "uploading"
    assert first.json()["bytes_received"] == mid

    wrong = _put(client, admin_headers, session_id, payload[mid:], offset=0, complete=True)
    assert wrong.status_code == 409
    assert "Upload-Offset mismatch" in wrong.json()["detail"]

    # Retry already-accepted chunk (stale offset) → 409
    retry = _put(client, admin_headers, session_id, payload[:mid], offset=0, complete=False)
    assert retry.status_code == 409

    second = _put(client, admin_headers, session_id, payload[mid:], offset=mid, complete=True)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "completed"
    assert second.json()["bytes_received"] == len(payload)
    asset_id = created.json()["media_asset"]["id"]
    meta = client.get(f"/api/admin/media/assets/{asset_id}", headers=admin_headers).json()
    assert meta["checksum_sha256"] == hashlib.sha256(payload).hexdigest()


def test_resume_after_request_restart(client, admin_headers):
    payload = minimal_mp4(b"RESUME-DATA-OK")
    created = _create_session(client, admin_headers, size=len(payload))
    session_id = created.json()["session"]["id"]
    mid = 12
    assert (
        _put(client, admin_headers, session_id, payload[:mid], offset=0, complete=False).status_code
        == 200
    )

    # Simulate new request: only consult persisted progress.
    progress = client.get(f"/api/admin/media/sessions/{session_id}", headers=admin_headers).json()
    assert progress["bytes_received"] == mid
    assert progress["status"] == "uploading"

    final = _put(
        client,
        admin_headers,
        session_id,
        payload[mid:],
        offset=progress["bytes_received"],
        complete=True,
    )
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "completed"


def test_upload_after_cancel_and_complete_rejected(client, admin_headers):
    payload = minimal_mp4(b"\x00" * 8)
    created = _create_session(client, admin_headers, size=len(payload))
    session_id = created.json()["session"]["id"]
    assert (
        client.delete(f"/api/admin/media/sessions/{session_id}", headers=admin_headers).status_code
        == 200
    )
    assert (
        _put(client, admin_headers, session_id, payload, offset=0, complete=True).status_code == 409
    )

    created = _create_session(client, admin_headers, filename="done.mp4", size=len(payload))
    session_id = created.json()["session"]["id"]
    assert (
        _put(client, admin_headers, session_id, payload, offset=0, complete=True).status_code == 200
    )
    assert (
        _put(client, admin_headers, session_id, payload, offset=0, complete=True).status_code == 409
    )


def test_upload_after_failed_and_expired_rejected(client, admin_headers, db_session):
    from datetime import UTC, datetime, timedelta

    from app.models.media_assets import UploadSession

    payload = minimal_mp4(b"\x00" * 8)
    # Fail via incomplete Upload-Complete, then reject further chunks.
    created = _create_session(client, admin_headers, filename="fail.mp4", size=len(payload))
    session_id = created.json()["session"]["id"]
    assert (
        _put(client, admin_headers, session_id, payload[:4], offset=0, complete=True).status_code
        == 400
    )
    progress = client.get(f"/api/admin/media/sessions/{session_id}", headers=admin_headers).json()
    assert progress["status"] == "failed"
    assert (
        _put(client, admin_headers, session_id, payload, offset=0, complete=True).status_code == 409
    )

    # Expire a pending session and reject upload with 410.
    created = _create_session(client, admin_headers, filename="exp.mp4", size=len(payload))
    session_id = created.json()["session"]["id"]
    row = db_session.get(UploadSession, session_id)
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    db_session.add(row)
    db_session.commit()
    expired = _put(client, admin_headers, session_id, payload, offset=0, complete=True)
    assert expired.status_code == 410
    progress = client.get(f"/api/admin/media/sessions/{session_id}", headers=admin_headers).json()
    assert progress["status"] == "failed"


def test_content_signature_validation(client, admin_headers):
    exe = pe_executable()
    created = _create_session(client, admin_headers, filename="evil.mp4", size=len(exe))
    resp = _put(
        client, admin_headers, created.json()["session"]["id"], exe, offset=0, complete=True
    )
    assert resp.status_code == 400
    assert "Executable" in resp.json()["detail"] or "signature" in resp.json()["detail"].lower()

    created = _create_session(
        client,
        admin_headers,
        filename="evil.bin",
        size=len(exe),
        mime="application/octet-stream",
    )
    # .bin is not a recognized media extension for octet-stream
    # sanitize allows .bin; content check should fail on extension or signature
    # Use .mp4 name with octet-stream + MZ payload
    created = _create_session(
        client,
        admin_headers,
        filename="evil2.mp4",
        size=len(exe),
        mime="application/octet-stream",
    )
    resp = _put(
        client,
        admin_headers,
        created.json()["session"]["id"],
        exe,
        offset=0,
        complete=True,
        filename="evil2.mp4",
        mime="application/octet-stream",
    )
    assert resp.status_code == 400

    mp4 = minimal_mp4(b"\x00" * 16)
    created = _create_session(client, admin_headers, filename="ok.mp4", size=len(mp4))
    assert (
        _put(
            client, admin_headers, created.json()["session"]["id"], mp4, offset=0, complete=True
        ).status_code
        == 200
    )

    jpeg = minimal_jpeg(b"\x00" * 8)
    created = _create_session(
        client,
        admin_headers,
        filename="poster.jpg",
        size=len(jpeg),
        mime="image/jpeg",
        category="posters",
    )
    assert (
        _put(
            client,
            admin_headers,
            created.json()["session"]["id"],
            jpeg,
            offset=0,
            complete=True,
            filename="poster.jpg",
            mime="image/jpeg",
        ).status_code
        == 200
    )

    png = minimal_png(b"\x00" * 8)
    created = _create_session(
        client,
        admin_headers,
        filename="art.png",
        size=len(png),
        mime="image/png",
        category="posters",
    )
    assert (
        _put(
            client,
            admin_headers,
            created.json()["session"]["id"],
            png,
            offset=0,
            complete=True,
            filename="art.png",
            mime="image/png",
        ).status_code
        == 200
    )

    # MIME/extension mismatch: .png declared as video/mp4
    created = _create_session(
        client, admin_headers, filename="bad.png", size=len(png), mime="video/mp4"
    )
    # create may succeed; put fails on content vs mime/ext
    resp = _put(
        client,
        admin_headers,
        created.json()["session"]["id"],
        png,
        offset=0,
        complete=True,
        filename="bad.png",
        mime="video/mp4",
    )
    assert resp.status_code == 400

    # Unknown binary as mp4
    mystery = b"\x00\x01\x02\x03NOTAMEDIAFILE!!!!"
    created = _create_session(client, admin_headers, filename="mystery.mp4", size=len(mystery))
    resp = _put(
        client, admin_headers, created.json()["session"]["id"], mystery, offset=0, complete=True
    )
    assert resp.status_code == 400


def test_streaming_upload_checksum_and_storage_path(client, admin_headers):
    payload = minimal_mp4(b"hello-media-bytes")
    created = _create_session(client, admin_headers, size=len(payload))
    assert created.status_code == 201, created.text
    session_id = created.json()["session"]["id"]
    asset_id = created.json()["media_asset"]["id"]

    progress = client.get(f"/api/admin/media/sessions/{session_id}", headers=admin_headers)
    assert progress.status_code == 200
    assert progress.json()["status"] == "pending"

    uploaded = _put(client, admin_headers, session_id, payload, offset=0, complete=True)
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
    payload = minimal_mp4(b"duplicate-bytes-xx")
    first = _create_session(client, admin_headers, filename="one.mp4", size=len(payload))
    assert (
        _put(
            client, admin_headers, first.json()["session"]["id"], payload, offset=0, complete=True
        ).status_code
        == 200
    )

    second = _create_session(client, admin_headers, filename="two.mp4", size=len(payload))
    dup = _put(
        client, admin_headers, second.json()["session"]["id"], payload, offset=0, complete=True
    )
    assert dup.status_code == 409
    assert "Duplicate" in dup.json()["detail"]
    monkeypatch.delenv("UPLOAD_REJECT_DUPLICATE_CHECKSUM", raising=False)
    get_settings.cache_clear()


def test_concurrent_duplicate_checksum_finalization(client, admin_headers, monkeypatch):
    """Two simultaneous completes with the same checksum must not both succeed."""
    import concurrent.futures

    monkeypatch.setenv("UPLOAD_REJECT_DUPLICATE_CHECKSUM", "true")
    get_settings.cache_clear()
    payload = minimal_mp4(b"concurrent-dup-payload!!")

    sessions = []
    for name in ("c1.mp4", "c2.mp4"):
        created = _create_session(client, admin_headers, filename=name, size=len(payload))
        assert created.status_code == 201
        sessions.append(created.json()["session"]["id"])

    def _finalize(session_id: str):
        return _put(client, admin_headers, session_id, payload, offset=0, complete=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_finalize, sessions))

    statuses = sorted(r.status_code for r in results)
    assert 200 in statuses
    assert 409 in statuses
    assert statuses.count(200) == 1

    completed = [
        client.get(f"/api/admin/media/sessions/{sid}", headers=admin_headers).json()["status"]
        for sid in sessions
    ]
    assert completed.count("completed") == 1
    assert completed.count("failed") == 1
    monkeypatch.delenv("UPLOAD_REJECT_DUPLICATE_CHECKSUM", raising=False)
    get_settings.cache_clear()


def test_large_file_streaming(client, admin_headers):
    payload = minimal_mp4(b"abcdefghij" * 1024 * 20)  # ~20KB+ header
    created = _create_session(client, admin_headers, filename="large.mp4", size=len(payload))
    assert created.status_code == 201
    session_id = created.json()["session"]["id"]
    uploaded = _put(client, admin_headers, session_id, payload, offset=0, complete=True)
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["bytes_received"] == len(payload)
    asset_id = created.json()["media_asset"]["id"]
    meta = client.get(f"/api/admin/media/assets/{asset_id}", headers=admin_headers).json()
    assert meta["checksum_sha256"] == hashlib.sha256(payload).hexdigest()


def test_upload_crosses_mid_progress_flush_boundary(client, admin_headers):
    """Regression: mid-upload progress commits must not double-count bytes.

    Progress flushes every 8 MiB. Uploads larger than that previously failed with
    ``Uploaded size exceeds declared size_bytes`` after the first flush.
    """
    # 8 MiB + 256 KiB of payload body after a valid ftyp/mdat header.
    body = b"x" * ((8 * 1024 * 1024) + (256 * 1024))
    payload = minimal_mp4(body)
    created = _create_session(
        client, admin_headers, filename="over-8mb.mp4", size=len(payload)
    )
    assert created.status_code == 201
    session_id = created.json()["session"]["id"]
    uploaded = _put(client, admin_headers, session_id, payload, offset=0, complete=True)
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["status"] == "completed"
    assert uploaded.json()["bytes_received"] == len(payload)


def test_storage_layout_and_path_generation():
    root = ensure_media_layout()
    for name in ("originals", "posters", "backdrops", "trailers", "subtitles", "temp"):
        assert (root / name).is_dir()
    assert root == media_root()
    assert Path(root).is_absolute()


def test_list_media_assets(client, admin_headers):
    payload = minimal_mp4(b"list-me")
    created = _create_session(client, admin_headers, filename="listed.mp4", size=len(payload))
    _put(client, admin_headers, created.json()["session"]["id"], payload, offset=0, complete=True)
    listed = client.get("/api/admin/media/assets", headers=admin_headers)
    assert listed.status_code == 200
    body = listed.json()
    assert "data" in body
    assert any(item["original_filename"] == "listed.mp4" for item in body["data"])
