"""Media processing API, worker, and job lifecycle tests."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.media_assets import MediaAsset, new_uuid
from app.models.media_processing import MediaProcessingJob
from app.services.media_processing.jobs import (
    cancel_job,
    claim_next_job,
    execute_probe_job,
    queue_probe_job,
    recover_stale_jobs,
)
from app.services.media_processing.worker import run_once
from app.services.storage import asset_storage_path, ensure_media_layout, relative_media_path


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
        hashed_password=hash_password("processing-admin-pass-ok"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})


def _tiny_mp4(path: Path, *, unique_tag: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    colors = (
        "black",
        "white",
        "red",
        "green",
        "blue",
        "yellow",
        "cyan",
        "magenta",
        "gray",
        "orange",
    )
    color = colors[abs(hash(unique_tag or str(path))) % len(colors)]
    freq = 400 + (abs(hash(unique_tag or str(path))) % 200)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=64x64:d=0.25",
            "-f",
            "lavfi",
            "-i",
            f"sine=f={freq}:d=0.25",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            "-metadata",
            f"comment={unique_tag}",
            str(path),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def _completed_asset(
    db_session, *, filename: str = "clip.mp4", category: str = "originals"
) -> MediaAsset:
    ensure_media_layout()
    asset_id = new_uuid()
    stored = f"{asset_id}.mp4"
    dest = asset_storage_path(category=category, asset_id=asset_id, stored_filename=stored)
    _tiny_mp4(dest, unique_tag=asset_id)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    asset = MediaAsset(
        id=asset_id,
        original_filename=filename,
        stored_filename=stored,
        mime_type="video/mp4",
        extension="mp4",
        size_bytes=dest.stat().st_size,
        checksum_sha256=digest,
        storage_backend="local",
        storage_path=relative_media_path(dest),
        category=category,
        upload_status="completed",
        processing_status="none",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def test_processing_rbac(client, db_session):
    reader = _make_admin(db_session, username="proc-reader", permissions=["processing.read"])
    manager = _make_admin(db_session, username="proc-manager", permissions=["processing.manage"])
    other = _make_admin(db_session, username="movies-only", permissions=["movies.manage"])

    assert (
        client.get("/api/admin/media/processing/jobs", headers=_headers(reader)).status_code == 200
    )
    assert (
        client.post(
            "/api/admin/media/assets/missing/processing/probe", headers=_headers(reader)
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/admin/media/assets/missing/processing/probe", headers=_headers(other)
        ).status_code
        == 403
    )
    # manager gets 404 for missing asset rather than 403
    assert (
        client.post(
            "/api/admin/media/assets/missing/processing/probe", headers=_headers(manager)
        ).status_code
        == 404
    )


def test_feature_disabled(client, admin_headers, monkeypatch):
    monkeypatch.setenv("ENABLE_MEDIA_PROCESSING", "false")
    get_settings.cache_clear()
    assert client.get("/api/admin/media/processing/jobs", headers=admin_headers).status_code == 503
    monkeypatch.setenv("ENABLE_MEDIA_PROCESSING", "true")
    get_settings.cache_clear()


def test_queue_probe_requires_completed_upload(client, admin_headers, db_session):
    asset = MediaAsset(
        id=new_uuid(),
        original_filename="pending.mp4",
        stored_filename="pending.mp4",
        mime_type="video/mp4",
        extension="mp4",
        size_bytes=1,
        storage_backend="local",
        storage_path="originals/x/pending.mp4",
        category="originals",
        upload_status="pending",
        processing_status="none",
    )
    db_session.add(asset)
    db_session.commit()
    resp = client.post(
        f"/api/admin/media/assets/{asset.id}/processing/probe", headers=admin_headers
    )
    assert resp.status_code == 409


def test_create_list_get_retry_cancel_flow(client, admin_headers, db_session):
    asset = _completed_asset(db_session)
    created = client.post(
        f"/api/admin/media/assets/{asset.id}/processing/probe", headers=admin_headers
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["created"] is True
    job_id = body["job"]["id"]
    assert body["job"]["status"] == "queued"

    dup = client.post(f"/api/admin/media/assets/{asset.id}/processing/probe", headers=admin_headers)
    assert dup.status_code == 200
    assert dup.json()["created"] is False
    assert dup.json()["job"]["id"] == job_id

    listed = client.get(f"/api/admin/media/assets/{asset.id}/processing", headers=admin_headers)
    assert listed.status_code == 200
    assert any(item["id"] == job_id for item in listed.json()["data"])

    got = client.get(f"/api/admin/media/processing/jobs/{job_id}", headers=admin_headers)
    assert got.status_code == 200
    assert got.json()["id"] == job_id

    cancelled = client.delete(f"/api/admin/media/processing/jobs/{job_id}", headers=admin_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    # Retry rejected for cancelled
    assert (
        client.post(
            f"/api/admin/media/processing/jobs/{job_id}/retry", headers=admin_headers
        ).status_code
        == 409
    )


@pytest.mark.parametrize("category", ["originals", "trailers", "subtitles"])
def test_upload_enqueue_probe_worker_reads_file(db_session, category):
    """Regression: worker must resolve storage_path under every upload category.

    Production failure mode: API wrote trailers/... but worker had no trailers
    volume mount → empty container-local dir → "Uploaded media file is missing".
    """
    from app.services.media_processing.paths import resolve_completed_asset_path

    settings = get_settings()
    asset = _completed_asset(db_session, filename=f"{category}-probe.mp4", category=category)
    assert asset.storage_path.startswith(f"{category}/")
    resolved = resolve_completed_asset_path(asset)
    assert resolved.is_file()
    assert resolved.read_bytes()  # worker can actually read bytes

    job, _ = queue_probe_job(db_session, settings=settings, asset=asset, admin_id=None)
    claimed = claim_next_job(db_session, settings=settings, worker_id=f"probe-{category}")
    assert claimed is not None
    result = execute_probe_job(db_session, settings=settings, job=claimed)
    assert result.status == "completed", result.error_message
    db_session.refresh(asset)
    assert asset.processing_status == "completed"
    assert asset.duration_seconds is not None or asset.width is not None or asset.video_codec


def test_worker_probe_success_persists_metadata(client, admin_headers, db_session):
    settings = get_settings()
    asset = _completed_asset(db_session, filename="probe-ok.mp4")
    before = Path(
        asset_storage_path(
            category="originals", asset_id=asset.id, stored_filename=asset.stored_filename
        )
    ).read_bytes()
    job, _ = queue_probe_job(db_session, settings=settings, asset=asset, admin_id=None)
    claimed = claim_next_job(db_session, settings=settings, worker_id="test-worker")
    assert claimed is not None
    assert claimed.id == job.id
    result = execute_probe_job(db_session, settings=settings, job=claimed)
    assert result.status == "completed"
    db_session.refresh(asset)
    assert asset.processing_status == "completed"
    assert asset.video_codec is not None
    assert asset.audio_codec is not None
    assert asset.probed_at is not None
    assert asset.probe_json is not None
    after = Path(
        asset_storage_path(
            category="originals", asset_id=asset.id, stored_filename=asset.stored_filename
        )
    ).read_bytes()
    assert before == after


def test_two_workers_cannot_claim_same_job(db_session):
    settings = get_settings()
    asset = _completed_asset(db_session, filename="race.mp4")
    queue_probe_job(db_session, settings=settings, asset=asset, admin_id=None)
    first = claim_next_job(db_session, settings=settings, worker_id="w1")
    second = claim_next_job(db_session, settings=settings, worker_id="w2")
    assert first is not None
    assert second is None


def test_transient_failure_schedules_retry(db_session, monkeypatch):
    settings = get_settings()
    asset = _completed_asset(db_session, filename="retry.mp4")
    job, _ = queue_probe_job(db_session, settings=settings, asset=asset, admin_id=None)
    claimed = claim_next_job(db_session, settings=settings, worker_id="w-retry")
    assert claimed is not None

    def boom(*_a, **_k):
        from app.services.media_processing.errors import TransientProcessingError

        raise TransientProcessingError("temporary blip", code="temp_db")

    monkeypatch.setattr(
        "app.services.media_processing.jobs.run_ffprobe",
        boom,
    )
    result = execute_probe_job(db_session, settings=settings, job=claimed)
    assert result.status == "retry_wait"
    assert result.next_retry_at is not None
    assert result.attempt_count == 1


def test_max_attempts_final_failure(db_session, monkeypatch):
    settings = get_settings()
    asset = _completed_asset(db_session, filename="final-fail.mp4")
    job, _ = queue_probe_job(db_session, settings=settings, asset=asset, admin_id=None)
    job.max_attempts = 1
    db_session.add(job)
    db_session.commit()

    def boom(*_a, **_k):
        from app.services.media_processing.errors import TransientProcessingError

        raise TransientProcessingError("still bad", code="temp")

    monkeypatch.setattr("app.services.media_processing.jobs.run_ffprobe", boom)
    claimed = claim_next_job(db_session, settings=settings, worker_id="w-final")
    result = execute_probe_job(db_session, settings=settings, job=claimed)
    assert result.status == "failed"


def test_cancel_before_and_during_execution(db_session, monkeypatch):
    settings = get_settings()
    asset = _completed_asset(db_session, filename="cancel.mp4")
    job, _ = queue_probe_job(db_session, settings=settings, asset=asset, admin_id=None)
    cancelled = cancel_job(db_session, job)
    assert cancelled.status == "cancelled"
    assert claim_next_job(db_session, settings=settings, worker_id="w") is None

    asset2 = _completed_asset(db_session, filename="cancel-run.mp4")
    job2, _ = queue_probe_job(db_session, settings=settings, asset=asset2, admin_id=None)
    claimed = claim_next_job(db_session, settings=settings, worker_id="w-run")
    assert claimed is not None

    def slow_probe(settings, media_path, cancel_check=None):
        # Request cancel mid-flight.
        cancel_job(db_session, claimed)
        if cancel_check and cancel_check():
            from app.services.media_processing.errors import ProbeCancelledError

            raise ProbeCancelledError("cancelled")
        raise AssertionError("cancel_check should have fired")

    monkeypatch.setattr("app.services.media_processing.jobs.run_ffprobe", slow_probe)
    result = execute_probe_job(db_session, settings=settings, job=claimed)
    assert result.status == "cancelled"


def test_stale_job_recovery(db_session):
    settings = get_settings()
    asset = _completed_asset(db_session, filename="stale.mp4")
    job, _ = queue_probe_job(db_session, settings=settings, asset=asset, admin_id=None)
    claimed = claim_next_job(db_session, settings=settings, worker_id="dead")
    assert claimed is not None
    claimed.heartbeat_at = datetime.now(UTC) - timedelta(
        seconds=settings.media_processing_stale_after_seconds + 5
    )
    db_session.add(claimed)
    db_session.commit()
    recovered = recover_stale_jobs(db_session, settings=settings)
    assert recovered == 1
    db_session.refresh(claimed)
    assert claimed.status in {"retry_wait", "failed"}


def test_retry_failed_job_api(client, admin_headers, db_session):
    settings = get_settings()
    asset = _completed_asset(db_session, filename="retry-api.mp4")
    job, _ = queue_probe_job(db_session, settings=settings, asset=asset, admin_id=None)
    job.status = "failed"
    job.attempt_count = 1
    job.error_message = "boom"
    db_session.add(job)
    db_session.commit()
    resp = client.post(f"/api/admin/media/processing/jobs/{job.id}/retry", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


def test_run_once_and_queued_survive_restart(db_session):
    settings = get_settings()
    asset = _completed_asset(db_session, filename="restart.mp4")
    queue_probe_job(db_session, settings=settings, asset=asset, admin_id=None)
    # Simulated worker restart: queued job still claimable.
    assert run_once(db_session, settings=settings, worker_id="restart-w") is True
    db_session.refresh(asset)
    assert asset.processing_status == "completed"


def test_corrupt_media_records_diagnostics(db_session):
    settings = get_settings()
    ensure_media_layout()
    asset_id = new_uuid()
    stored = f"{asset_id}.mp4"
    dest = asset_storage_path(category="originals", asset_id=asset_id, stored_filename=stored)
    dest.write_bytes(b"not-a-real-media-file!!!!")
    asset = MediaAsset(
        id=asset_id,
        original_filename="bad.mp4",
        stored_filename=stored,
        mime_type="video/mp4",
        extension="mp4",
        size_bytes=dest.stat().st_size,
        checksum_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
        storage_backend="local",
        storage_path=relative_media_path(dest),
        category="originals",
        upload_status="completed",
        processing_status="none",
    )
    db_session.add(asset)
    db_session.commit()
    job, _ = queue_probe_job(db_session, settings=settings, asset=asset, admin_id=None)
    claimed = claim_next_job(db_session, settings=settings, worker_id="bad")
    result = execute_probe_job(db_session, settings=settings, job=claimed)
    assert result.status in {"failed", "retry_wait"}
    assert result.error_message


def test_concurrent_queue_requests(client, admin_headers, db_session):
    """Active probe uniqueness is enforced by the partial unique index."""
    from sqlalchemy.exc import IntegrityError

    asset = _completed_asset(db_session, filename="concurrent-q.mp4")
    first = client.post(
        f"/api/admin/media/assets/{asset.id}/processing/probe", headers=admin_headers
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/admin/media/assets/{asset.id}/processing/probe", headers=admin_headers
    )
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["job"]["id"] == first.json()["job"]["id"]

    # Direct ORM insert of a second active probe must fail the unique index.
    dup = MediaProcessingJob(
        id=new_uuid(),
        media_asset_id=asset.id,
        job_type="probe",
        status="queued",
        priority=100,
        attempt_count=0,
        max_attempts=3,
        progress_percent=0,
        current_step="queued",
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    active = (
        db_session.query(MediaProcessingJob)
        .filter(
            MediaProcessingJob.media_asset_id == asset.id,
            MediaProcessingJob.status.in_(("queued", "running", "retry_wait")),
        )
        .all()
    )
    assert len(active) == 1
