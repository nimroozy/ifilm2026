"""HLS encoding unit, API, and worker tests (local filesystem)."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.media_assets import MediaAsset, new_uuid
from app.services.media_processing.encode_job import (
    queue_encode_hls_job,
)
from app.services.media_processing.hls_encode import build_hls_rendition_argv, gop_size
from app.services.media_processing.jobs import (
    cancel_job,
)
from app.services.media_processing.package_paths import work_package_dir
from app.services.media_processing.profiles import (
    even_width_for_height,
    select_profiles_for_source,
)
from app.services.media_processing.worker import run_once
from app.services.storage import (
    asset_storage_path,
    ensure_media_layout,
    media_root,
    relative_media_path,
)


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
        hashed_password=hash_password("hls-admin-pass-ok"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})


def _mp4(
    path: Path,
    *,
    size: str = "640x360",
    duration: float = 1.0,
    unique_tag: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s={size}:d={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=f=440:d={duration}",
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


def _completed_probed_asset(
    db_session,
    *,
    filename: str = "clip.mp4",
    size: str = "640x360",
    duration: float = 1.0,
) -> MediaAsset:
    ensure_media_layout()
    asset_id = new_uuid()
    stored = f"{asset_id}.mp4"
    dest = asset_storage_path(category="originals", asset_id=asset_id, stored_filename=stored)
    _mp4(dest, size=size, duration=duration, unique_tag=asset_id)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    width, height = (int(part) for part in size.split("x"))
    asset = MediaAsset(
        id=asset_id,
        original_filename=filename,
        stored_filename=stored,
        mime_type="video/mp4",
        extension="mp4",
        size_bytes=dest.stat().st_size,
        checksum_sha256=digest,
        width=width,
        height=height,
        duration_seconds=duration,
        video_codec="h264",
        audio_codec="aac",
        audio_stream_count=1,
        video_frame_rate=25.0,
        storage_backend="local",
        storage_path=relative_media_path(dest),
        category="originals",
        upload_status="completed",
        processing_status="completed",
        probed_at=datetime.now(UTC),
        probe_version="ffprobe-json-v1",
        probe_json={"format": {"format_name": "mov,mp4"}},
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def test_profile_selection_never_upscales(db_session):
    settings = get_settings()
    selected = select_profiles_for_source(db_session, settings=settings, source_height=360)
    heights = [p.height for p in selected]
    assert heights == [240, 360]
    assert all(h <= 360 for h in heights)
    assert 480 not in heights
    assert 1080 not in heights


def test_even_width_and_gop():
    assert even_width_for_height(1280, 720, 360) == 640
    assert gop_size(frame_rate=25.0, segment_seconds=6) == 150


def test_ffmpeg_argv_is_list_no_shell():
    from app.models.media_encoding import MediaEncodingProfile

    profile = MediaEncodingProfile(
        id="p1",
        name="hls_360p",
        label="360p",
        height=360,
        video_bitrate=800_000,
        audio_bitrate=96_000,
        maxrate=880_000,
        bufsize=1_600_000,
    )
    argv = build_hls_rendition_argv(
        ffmpeg_binary="ffmpeg",
        source=Path("/tmp/in.mp4"),
        playlist_path=Path("/tmp/out/360p/index.m3u8"),
        segment_pattern=Path("/tmp/out/360p/segment_%03d.ts"),
        profile=profile,
        target_width=640,
        target_height=360,
        segment_seconds=6,
        gop=150,
        preset="veryfast",
        has_audio=True,
    )
    assert isinstance(argv, list)
    assert argv[0] == "ffmpeg"
    assert "-progress" in argv
    assert "pipe:1" in argv
    assert "-hls_time" in argv
    assert "6" in argv


def test_encode_requires_probe(client, admin_headers, db_session):
    ensure_media_layout()
    asset_id = new_uuid()
    stored = f"{asset_id}.mp4"
    dest = asset_storage_path(category="originals", asset_id=asset_id, stored_filename=stored)
    _mp4(dest, size="640x360", unique_tag=asset_id)
    asset = MediaAsset(
        id=asset_id,
        original_filename="noprobe.mp4",
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
        probed_at=None,
    )
    db_session.add(asset)
    db_session.commit()
    resp = client.post(
        f"/api/admin/media/assets/{asset.id}/processing/encode-hls",
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_queue_encode_duplicate_active(client, admin_headers, db_session):
    asset = _completed_probed_asset(db_session)
    first = client.post(
        f"/api/admin/media/assets/{asset.id}/processing/encode-hls",
        headers=admin_headers,
    )
    assert first.status_code == 201, first.text
    dup = client.post(
        f"/api/admin/media/assets/{asset.id}/processing/encode-hls",
        headers=admin_headers,
    )
    assert dup.status_code == 200
    assert dup.json()["created"] is False
    assert dup.json()["job"]["id"] == first.json()["job"]["id"]


def test_list_encoding_profiles(client, admin_headers):
    resp = client.get("/api/admin/media/encoding/profiles", headers=admin_headers)
    assert resp.status_code == 200
    labels = {item["label"] for item in resp.json()["data"]}
    assert labels == {"240p", "360p", "480p", "720p", "1080p"}


def test_worker_hls_encode_e2e_no_upscale_and_checksum(db_session):
    settings = get_settings()
    # 360p source → only 240p + 360p
    asset = _completed_probed_asset(db_session, size="640x360", duration=1.2, filename="e2e.mp4")
    source = Path(
        asset_storage_path(
            category="originals", asset_id=asset.id, stored_filename=asset.stored_filename
        )
    )
    before = source.read_bytes()
    before_sha = hashlib.sha256(before).hexdigest()

    job, package, created = queue_encode_hls_job(
        db_session, settings=settings, asset=asset, admin_id=None
    )
    assert created is True
    assert package.status == "pending"
    # Partial package must not look completed
    assert package.master_playlist_path is None

    assert run_once(db_session, settings=settings, worker_id="hls-worker") is True
    db_session.refresh(job)
    db_session.refresh(package)
    db_session.refresh(asset)

    assert job.status == "completed", (job.error_code, job.error_message)
    assert package.status == "completed"
    assert package.is_active is True
    assert package.activated_at is not None
    assert package.master_playlist_path
    assert package.storage_path
    assert package.rendition_count == 2
    labels = sorted(r.label for r in package.renditions)
    assert labels == ["240p", "360p"]
    for rendition in package.renditions:
        assert rendition.height <= 360
        assert rendition.status == "completed"

    master = media_root() / package.master_playlist_path
    assert master.is_file()
    text = master.read_text(encoding="utf-8")
    assert "#EXT-X-STREAM-INF" in text
    assert "240p/index.m3u8" in text
    assert "360p/index.m3u8" in text
    assert "720p" not in text
    assert "1080p" not in text

    after = source.read_bytes()
    assert after == before
    assert hashlib.sha256(after).hexdigest() == before_sha

    # API must not expose incomplete packages as completed — this one is completed.
    assert package.work_path is None
    assert not work_package_dir(job.id, create=False).exists()


def test_cancel_encode_cleans_work_dir(db_session):
    settings = get_settings()
    asset = _completed_probed_asset(db_session, size="640x360", filename="cancel.mp4")
    job, package, _ = queue_encode_hls_job(
        db_session, settings=settings, asset=asset, admin_id=None
    )
    work = work_package_dir(job.id)
    (work / "junk.txt").write_text("partial", encoding="utf-8")
    package.work_path = relative_media_path(work)
    package.status = "encoding"
    db_session.add(package)
    db_session.commit()

    cancelled = cancel_job(db_session, job)
    assert cancelled.status == "cancelled"
    db_session.refresh(package)
    assert package.status == "cancelled"
    assert package.work_path is None
    assert not work.exists()


def test_partial_package_paths_hidden_in_api(client, admin_headers, db_session):
    asset = _completed_probed_asset(db_session, filename="hide.mp4")
    settings = get_settings()
    job, package, _ = queue_encode_hls_job(
        db_session, settings=settings, asset=asset, admin_id=None
    )
    package.status = "encoding"
    package.storage_path = "packages/fake/master"
    package.master_playlist_path = "packages/fake/master.m3u8"
    package.rendition_count = 3
    db_session.add(package)
    db_session.commit()

    resp = client.get(f"/api/admin/media/packages/{package.id}", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "encoding"
    assert body["storage_path"] is None
    assert body["master_playlist_path"] is None
    assert body["renditions"] == []
    assert body["rendition_count"] == 0


def test_encode_rbac(client, db_session):
    reader = _make_admin(db_session, username="hls-reader", permissions=["processing.read"])
    other = _make_admin(db_session, username="movies-only-hls", permissions=["movies.manage"])
    asset = _completed_probed_asset(db_session, filename="rbac.mp4")
    assert (
        client.post(
            f"/api/admin/media/assets/{asset.id}/processing/encode-hls",
            headers=_headers(reader),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/admin/media/assets/{asset.id}/processing/encode-hls",
            headers=_headers(other),
        ).status_code
        == 403
    )
