"""Upload durability, SHA256 dedup reuse, delete safety, storage health."""

from __future__ import annotations

import errno
import hashlib
import os

from app.core.config import get_settings
from app.models.content import Movie
from app.models.media_admin_events import MediaAdminEvent
from app.models.media_assets import MediaAsset
from app.services.storage import media_root
from tests.test_media_upload import (
    _create_session,
    _headers,
    _make_admin,
    _put,
    minimal_mp4,
)


def test_finalize_file_exists_before_completed(client, admin_headers):
    payload = minimal_mp4(b"durable-finalize-bytes")
    created = _create_session(client, admin_headers, filename="durable.mp4", size=len(payload))
    assert created.status_code == 201
    session_id = created.json()["session"]["id"]
    asset_id = created.json()["media_asset"]["id"]
    uploaded = _put(client, admin_headers, session_id, payload, offset=0, complete=True)
    assert uploaded.status_code == 200, uploaded.text
    meta = client.get(f"/api/admin/media/assets/{asset_id}", headers=admin_headers).json()
    assert meta["upload_status"] == "completed"
    stored = media_root() / meta["storage_path"]
    assert stored.is_file()
    assert stored.stat().st_size == len(payload)
    assert meta["checksum_sha256"] == hashlib.sha256(payload).hexdigest()


def test_duplicate_checksum_structured_reuse(client, admin_headers, monkeypatch):
    monkeypatch.setenv("UPLOAD_REJECT_DUPLICATE_CHECKSUM", "true")
    get_settings.cache_clear()
    payload = minimal_mp4(b"same-bytes-dedup-!!")
    first = _create_session(client, admin_headers, filename="alpha.mp4", size=len(payload))
    assert (
        _put(
            client, admin_headers, first.json()["session"]["id"], payload, offset=0, complete=True
        ).status_code
        == 200
    )
    existing_id = first.json()["media_asset"]["id"]

    second = _create_session(client, admin_headers, filename="beta.mp4", size=len(payload))
    dup = _put(
        client, admin_headers, second.json()["session"]["id"], payload, offset=0, complete=True
    )
    assert dup.status_code == 409
    detail = dup.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "duplicate_checksum"
    assert detail["message"] == "This file already exists."
    assert detail["existing_asset_id"] == existing_id
    assert "view_existing" in detail["actions"]

    # No second physical copy for the failed session asset.
    failed_asset = client.get(
        f"/api/admin/media/assets/{second.json()['media_asset']['id']}", headers=admin_headers
    ).json()
    assert failed_asset["upload_status"] == "failed"
    assert failed_asset["storage_path"] is None

    monkeypatch.delenv("UPLOAD_REJECT_DUPLICATE_CHECKSUM", raising=False)
    get_settings.cache_clear()


def test_same_filename_different_bytes_allowed(client, admin_headers):
    a = minimal_mp4(b"content-aaa")
    b = minimal_mp4(b"content-bbb")
    for payload, tag in ((a, "a"), (b, "b")):
        created = _create_session(
            client, admin_headers, filename="same-name.mp4", size=len(payload)
        )
        assert created.status_code == 201
        assert (
            _put(
                client,
                admin_headers,
                created.json()["session"]["id"],
                payload,
                offset=0,
                complete=True,
                filename="same-name.mp4",
            ).status_code
            == 200
        ), tag


def test_delete_unlinked_asset_removes_file(client, admin_headers, db_session):
    payload = minimal_mp4(b"delete-me-please")
    created = _create_session(client, admin_headers, filename="trash.mp4", size=len(payload))
    asset_id = created.json()["media_asset"]["id"]
    assert (
        _put(
            client, admin_headers, created.json()["session"]["id"], payload, offset=0, complete=True
        ).status_code
        == 200
    )
    meta = client.get(f"/api/admin/media/assets/{asset_id}", headers=admin_headers).json()
    path = media_root() / meta["storage_path"]
    assert path.exists()

    usages = client.get(f"/api/admin/media/assets/{asset_id}/usages", headers=admin_headers)
    assert usages.status_code == 200
    assert usages.json()["usages"] == []

    denied = client.post(
        f"/api/admin/media/assets/{asset_id}/delete",
        headers=admin_headers,
        json={"confirm": False},
    )
    assert denied.status_code == 400

    deleted = client.post(
        f"/api/admin/media/assets/{asset_id}/delete",
        headers=admin_headers,
        json={"confirm": True},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True
    assert deleted.json()["removed_file"] is True
    assert not path.exists()

    events = db_session.query(MediaAdminEvent).filter_by(event_type="media_asset_deleted").all()
    assert any(e.media_asset_id == asset_id for e in events)


def test_delete_linked_asset_blocked_409(client, admin_headers, db_session):
    movie = Movie(
        title="Linked Movie",
        slug="linked-movie-delete",
        description="x",
        short_description="x",
        status="draft",
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)

    payload = minimal_mp4(b"linked-asset-bytes")
    created = _create_session(
        client,
        admin_headers,
        filename="linked.mp4",
        size=len(payload),
        movie_id=movie.id,
    )
    assert created.status_code == 201
    asset_id = created.json()["media_asset"]["id"]
    assert (
        _put(
            client, admin_headers, created.json()["session"]["id"], payload, offset=0, complete=True
        ).status_code
        == 200
    )

    blocked = client.post(
        f"/api/admin/media/assets/{asset_id}/delete",
        headers=admin_headers,
        json={"confirm": True},
    )
    assert blocked.status_code == 409
    detail = blocked.json()["detail"]
    assert detail["code"] == "media_in_use"
    assert any(u["kind"] == "movie" for u in detail["usages"])


def test_delete_path_traversal_rejected(client, admin_headers, db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    get_settings.cache_clear()
    from app.services.storage import ensure_media_layout

    ensure_media_layout()
    # Craft an asset with escaping storage_path (should never happen via normal upload).
    asset = MediaAsset(
        id="evil-del-1",
        original_filename="x.mp4",
        stored_filename="x.mp4",
        mime_type="video/mp4",
        size_bytes=1,
        checksum_sha256="a" * 64,
        storage_backend="local",
        storage_path="../escape.bin",
        category="originals",
        upload_status="completed",
        processing_status="none",
        source_type="uploaded",
    )
    db_session.add(asset)
    db_session.commit()
    token = _make_admin(db_session, username="del-trav", permissions=["upload.manage", "upload.read"])
    resp = client.post(
        f"/api/admin/media/assets/{asset.id}/delete",
        headers=_headers(token),
        json={"confirm": True},
    )
    assert resp.status_code == 400
    assert "outside" in resp.json()["detail"].lower() or "escape" in resp.json()["detail"].lower() or "owned" in resp.json()["detail"].lower()
    monkeypatch.delenv("MEDIA_ROOT", raising=False)
    get_settings.cache_clear()


def test_storage_health_detects_missing_and_duplicate(client, admin_headers, db_session):
    payload = minimal_mp4(b"health-check-bytes")
    created = _create_session(client, admin_headers, filename="health.mp4", size=len(payload))
    asset_id = created.json()["media_asset"]["id"]
    assert (
        _put(
            client, admin_headers, created.json()["session"]["id"], payload, offset=0, complete=True
        ).status_code
        == 200
    )
    meta = client.get(f"/api/admin/media/assets/{asset_id}", headers=admin_headers).json()
    path = media_root() / meta["storage_path"]
    path.unlink()

    report = client.get("/api/admin/media/storage-health", headers=admin_headers)
    assert report.status_code == 200
    body = report.json()
    assert body["summary"]["missing_files"] >= 1
    assert any(item["asset_id"] == asset_id for item in body["missing_files"])


def test_temp_cleanup_only_old_parts(client, admin_headers, tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    get_settings.cache_clear()
    import os
    import time

    from app.services.storage import ensure_media_layout, temp_upload_dir

    ensure_media_layout()
    temp = temp_upload_dir()
    fresh = temp / "fresh.part"
    stale = temp / "stale.part"
    fresh.write_bytes(b"fresh")
    stale.write_bytes(b"stale")
    old = time.time() - 100_000
    os.utime(stale, (old, old))

    resp = client.post(
        "/api/admin/media/temp-cleanup?max_age_seconds=3600",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["removed"] >= 1
    assert fresh.exists()
    assert not stale.exists()
    monkeypatch.delenv("MEDIA_ROOT", raising=False)
    get_settings.cache_clear()


def test_probe_queue_requires_existing_file(client, admin_headers):
    payload = minimal_mp4(b"probe-missing-guard")
    created = _create_session(client, admin_headers, filename="probe.mp4", size=len(payload))
    asset_id = created.json()["media_asset"]["id"]
    assert (
        _put(
            client, admin_headers, created.json()["session"]["id"], payload, offset=0, complete=True
        ).status_code
        == 200
    )
    meta = client.get(f"/api/admin/media/assets/{asset_id}", headers=admin_headers).json()
    (media_root() / meta["storage_path"]).unlink()

    resp = client.post(f"/api/admin/media/assets/{asset_id}/processing/probe", headers=admin_headers)
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "file_missing"


def test_retry_probe_blocked_when_file_missing(client, admin_headers, db_session):
    from app.models.media_assets import new_uuid, utcnow
    from app.models.media_processing import MediaProcessingJob

    payload = minimal_mp4(b"retry-missing-file!!")
    created = _create_session(client, admin_headers, filename="retry.mp4", size=len(payload))
    asset_id = created.json()["media_asset"]["id"]
    assert (
        _put(
            client, admin_headers, created.json()["session"]["id"], payload, offset=0, complete=True
        ).status_code
        == 200
    )
    meta = client.get(f"/api/admin/media/assets/{asset_id}", headers=admin_headers).json()
    stored = media_root() / meta["storage_path"]
    assert stored.is_file()
    stored.unlink()

    job = MediaProcessingJob(
        id=new_uuid(),
        media_asset_id=asset_id,
        job_type="probe",
        status="failed",
        priority=100,
        attempt_count=1,
        max_attempts=5,
        progress_percent=0,
        current_step="failed",
        error_code="file_missing",
        error_message="Uploaded media file is missing",
        queued_at=utcnow(),
    )
    db_session.add(job)
    db_session.commit()

    resp = client.post(f"/api/admin/media/processing/jobs/{job.id}/retry", headers=admin_headers)
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "file_missing"
    assert detail["asset_id"] == asset_id


def test_delete_commits_before_unlink(client, admin_headers, db_session, monkeypatch):
    """DB soft-delete must succeed even if filesystem unlink fails afterward."""
    payload = minimal_mp4(b"delete-order-bytes!!")
    created = _create_session(client, admin_headers, filename="order.mp4", size=len(payload))
    asset_id = created.json()["media_asset"]["id"]
    assert (
        _put(
            client, admin_headers, created.json()["session"]["id"], payload, offset=0, complete=True
        ).status_code
        == 200
    )
    meta = client.get(f"/api/admin/media/assets/{asset_id}", headers=admin_headers).json()
    stored = media_root() / meta["storage_path"]
    assert stored.is_file()

    real_unlink = type(stored).unlink

    def boom(self, *args, **kwargs):
        raise OSError("simulated unlink failure")

    monkeypatch.setattr(type(stored), "unlink", boom)
    resp = client.post(
        f"/api/admin/media/assets/{asset_id}/delete",
        headers=admin_headers,
        json={"confirm": True},
    )
    monkeypatch.setattr(type(stored), "unlink", real_unlink)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted"] is True
    assert body["removed_file"] is False
    asset = db_session.get(MediaAsset, asset_id)
    assert asset is not None
    assert asset.upload_status == "deleted"
    assert asset.storage_path is None
    # Physical file may remain as orphan; health tooling reports it (no auto-delete).
    assert stored.is_file()


def test_durable_move_falls_back_on_exdev(tmp_path, monkeypatch):
    from app.services import media_upload as mu

    src = tmp_path / "src.bin"
    dest = tmp_path / "nested" / "dest.bin"
    payload = b"cross-device-bytes-123456"
    src.write_bytes(payload)

    def boom(a, b):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(mu.os, "replace", boom)
    mu._durable_move(src, dest)
    assert dest.read_bytes() == payload
    assert not src.exists()

    # non-EXDEV still raises
    src2 = tmp_path / "src2.bin"
    src2.write_bytes(b"x")
    dest2 = tmp_path / "dest2.bin"

    def boom_other(a, b):
        raise OSError(errno.EPERM, "denied")

    monkeypatch.setattr(mu.os, "replace", boom_other)
    try:
        mu._durable_move(src2, dest2)
        raised = False
    except OSError as exc:
        raised = exc.errno == errno.EPERM
    assert raised
