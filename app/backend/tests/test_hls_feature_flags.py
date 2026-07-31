"""Feature-flag coverage for media processing vs HLS encoding."""

from app.core.config import get_settings
from app.services.media_processing.worker import run_forever, validate_binaries


def test_media_processing_disabled_blocks_probe_and_encode(client, admin_headers, monkeypatch):
    monkeypatch.setenv("ENABLE_MEDIA_PROCESSING", "false")
    monkeypatch.setenv("ENABLE_HLS_ENCODING", "false")
    get_settings.cache_clear()

    status = client.get("/api/admin/media/processing/status", headers=admin_headers)
    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is False
    assert body["hls_encoding_enabled"] is False

    assert (
        client.post(
            "/api/admin/media/assets/any/processing/probe", headers=admin_headers
        ).status_code
        == 503
    )
    encode = client.post("/api/admin/media/assets/any/processing/encode-hls", headers=admin_headers)
    assert encode.status_code == 503
    assert encode.json()["detail"] == "Feature disabled"

    monkeypatch.setenv("ENABLE_MEDIA_PROCESSING", "true")
    monkeypatch.setenv("ENABLE_HLS_ENCODING", "true")
    get_settings.cache_clear()


def test_media_processing_enabled_hls_disabled_blocks_encode_allows_probe(
    client, admin_headers, db_session, monkeypatch
):
    import hashlib
    import subprocess
    from datetime import UTC, datetime

    from app.models.media_assets import MediaAsset, new_uuid
    from app.services.storage import asset_storage_path, ensure_media_layout, relative_media_path

    monkeypatch.setenv("ENABLE_MEDIA_PROCESSING", "true")
    monkeypatch.setenv("ENABLE_HLS_ENCODING", "false")
    get_settings.cache_clear()

    status = client.get("/api/admin/media/processing/status", headers=admin_headers)
    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is True
    assert body["hls_encoding_enabled"] is False

    ensure_media_layout()
    asset_id = new_uuid()
    stored = f"{asset_id}.mp4"
    dest = asset_storage_path(category="originals", asset_id=asset_id, stored_filename=stored)
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64:d=0.25",
            "-f",
            "lavfi",
            "-i",
            "sine=f=440:d=0.25",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(dest),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    asset = MediaAsset(
        id=asset_id,
        original_filename="flags.mp4",
        stored_filename=stored,
        mime_type="video/mp4",
        extension="mp4",
        size_bytes=dest.stat().st_size,
        checksum_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
        width=640,
        height=360,
        duration_seconds=1.0,
        storage_backend="local",
        storage_path=relative_media_path(dest),
        category="originals",
        upload_status="completed",
        processing_status="completed",
        probed_at=datetime.now(UTC),
        video_codec="h264",
        audio_codec="aac",
        audio_stream_count=1,
    )
    db_session.add(asset)
    db_session.commit()

    probe = client.post(
        f"/api/admin/media/assets/{asset.id}/processing/probe", headers=admin_headers
    )
    assert probe.status_code in {200, 201}, probe.text

    encode = client.post(
        f"/api/admin/media/assets/{asset.id}/processing/encode-hls", headers=admin_headers
    )
    assert encode.status_code == 503
    assert encode.json()["detail"] == "HLS encoding is disabled"

    profiles = client.get("/api/admin/media/encoding/profiles", headers=admin_headers)
    assert profiles.status_code == 503
    assert profiles.json()["detail"] == "HLS encoding is disabled"

    monkeypatch.setenv("ENABLE_HLS_ENCODING", "true")
    get_settings.cache_clear()


def test_both_flags_enabled_status(client, admin_headers, monkeypatch):
    monkeypatch.setenv("ENABLE_MEDIA_PROCESSING", "true")
    monkeypatch.setenv("ENABLE_HLS_ENCODING", "true")
    get_settings.cache_clear()
    status = client.get("/api/admin/media/processing/status", headers=admin_headers)
    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is True
    assert body["hls_encoding_enabled"] is True


def test_worker_starts_without_ffmpeg_when_hls_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_MEDIA_PROCESSING", "true")
    monkeypatch.setenv("ENABLE_HLS_ENCODING", "false")
    monkeypatch.setenv("FFMPEG_BINARY", str(tmp_path / "missing-ffmpeg"))
    monkeypatch.setenv("FFPROBE_BINARY", "ffprobe")
    get_settings.cache_clear()
    settings = get_settings()
    # Should not raise — ffmpeg is optional when HLS is disabled.
    validate_binaries(settings)


def test_worker_requires_ffmpeg_when_hls_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_MEDIA_PROCESSING", "true")
    monkeypatch.setenv("ENABLE_HLS_ENCODING", "true")
    monkeypatch.setenv("FFMPEG_BINARY", str(tmp_path / "missing-ffmpeg"))
    monkeypatch.setenv("FFPROBE_BINARY", "ffprobe")
    get_settings.cache_clear()
    settings = get_settings()
    try:
        validate_binaries(settings)
        raised = False
    except Exception:
        raised = True
    assert raised is True


def test_worker_exits_when_media_processing_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_MEDIA_PROCESSING", "false")
    get_settings.cache_clear()
    try:
        run_forever(settings=get_settings())
        code = 0
    except SystemExit as exc:
        code = int(exc.code or 0)
    assert code == 1
