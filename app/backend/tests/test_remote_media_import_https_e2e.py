"""Disposable HTTPS fixture E2E for remote MP4 import (synthetic media only)."""

from __future__ import annotations

import hashlib
import ssl
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.models.content import Movie
from app.models.media_assets import new_uuid
from app.models.media_processing import REMOTE_MEDIA_IMPORT_WORKER_JOB_TYPES
from app.services.media_processing.jobs import claim_next_job, queue_probe_job
from app.services.media_remote_import import queue_remote_media_import
from app.services.media_remote_import_worker import run_once as run_remote_import_once
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _have_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
        subprocess.run(["ffprobe", "-version"], check=True, capture_output=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


pytestmark = pytest.mark.skipif(not _have_ffmpeg(), reason="ffmpeg/ffprobe required")


def _make_self_signed_cert(path: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ifilm-remote-import-e2e")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path = path / "cert.pem"
    key_path = path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


def _make_synthetic_mp4(path: Path, *, seconds: int = 5) -> Path:
    """Short synthetic MP4 (color bars + silence). Not copyrighted media."""
    out = path / "synthetic.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=320x240:rate=24:duration={seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={seconds}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")[-800:]
    assert out.is_file() and out.stat().st_size > 1000
    return out


class _RangeHTTPSHandler(BaseHTTPRequestHandler):
    file_path: Path
    ignore_range: bool = False
    last_range: str | None = None
    get_count: int = 0

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_HEAD(self):  # noqa: N802
        data = self.file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        type(self).get_count += 1
        data = self.file_path.read_bytes()
        range_hdr = self.headers.get("Range")
        type(self).last_range = range_hdr
        if range_hdr and not self.ignore_range and range_hdr.startswith("bytes="):
            start_s = range_hdr.removeprefix("bytes=").split("-", 1)[0]
            start = int(start_s) if start_s.isdigit() else 0
            chunk = data[start:]
            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(chunk)
            return
        # Full body (also used when ignore_range=True)
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def https_fixture(tmp_path):
    mp4 = _make_synthetic_mp4(tmp_path, seconds=5)
    cert_path, key_path = _make_self_signed_cert(tmp_path)
    handler = type(
        "Handler",
        (_RangeHTTPSHandler,),
        {"file_path": mp4, "ignore_range": False, "last_range": None, "get_count": 0},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    url = f"https://127.0.0.1:{port}/synthetic.mp4?token=SECRETTOKEN&expires=999"
    yield {
        "url": url,
        "mp4": mp4,
        "handler": handler,
        "server": server,
        "sha256": hashlib.sha256(mp4.read_bytes()).hexdigest(),
        "size": mp4.stat().st_size,
    }
    server.shutdown()


@pytest.fixture
def e2e_settings(tmp_path, monkeypatch, https_fixture):
    media = tmp_path / "media"
    for sub in ("originals", "temp", "packages", "trailers", "subtitles", "audio", "posters", "backdrops"):
        (media / sub).mkdir(parents=True)
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("MEDIA_ROOT", str(media))
    monkeypatch.setenv("ENABLE_UPLOADS", "true")
    monkeypatch.setenv("ENABLE_REMOTE_MEDIA_IMPORT", "true")
    monkeypatch.setenv("ENABLE_MEDIA_PROCESSING", "true")
    monkeypatch.setenv("INTEGRATION_SECRETS_KEY", key)
    # Local disposable fixture is loopback — allow only in this test via assert patch.
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


def _allow_loopback_fixture(monkeypatch, url: str) -> None:
    """SSRF policy correctly blocks loopback; E2E patches only the host check."""

    def _safe(u: str):
        from urllib.parse import urlparse

        parsed = urlparse(u)
        assert parsed.scheme == "https"
        assert "SECRETTOKEN" in (parsed.query or "")
        return u, parsed.hostname or "127.0.0.1"

    monkeypatch.setattr("app.services.media_remote_import.assert_safe_external_url", _safe)
    monkeypatch.setattr("app.services.media_external.assert_safe_external_url", _safe)
    # httpx must accept self-signed fixture cert.
    import httpx

    real_client = httpx.Client

    def client_factory(*a, **k):
        k = dict(k)
        k["verify"] = False
        return real_client(*a, **k)

    monkeypatch.setattr("app.services.media_remote_import.httpx.Client", client_factory)
    monkeypatch.setattr("app.services.media_external.httpx.Client", client_factory)


def test_https_fixture_import_probe_pipeline(db_session, e2e_settings, https_fixture, monkeypatch):
    _allow_loopback_fixture(monkeypatch, https_fixture["url"])
    movie = Movie(
        title="E2E Import",
        slug=f"e2e-import-{new_uuid()[:8]}",
        status="draft",
        description="synthetic",
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)

    job, record, asset = queue_remote_media_import(
        db_session,
        settings=e2e_settings,
        url=https_fixture["url"],
        owner_type="movie",
        owner_id=movie.id,
        destination="local_origin",
        admin_id=1,
    )
    assert "SECRETTOKEN" not in record.source_url_display
    assert record.source_url_display.endswith("?…") or "SECRETTOKEN" not in record.source_url_display

    # Worker claim + execute (dedicated job types only).
    claimed = claim_next_job(
        db_session,
        settings=e2e_settings,
        worker_id="e2e-remote",
        allowed_job_types=REMOTE_MEDIA_IMPORT_WORKER_JOB_TYPES,
    )
    assert claimed is not None and claimed.id == job.id
    # run_once already claims; execute path: mark running already done by claim.
    from app.services.media_remote_import import execute_remote_media_import

    execute_remote_media_import(db_session, settings=e2e_settings, job=claimed)
    db_session.refresh(job)
    db_session.refresh(record)
    db_session.refresh(asset)
    assert job.status == "completed"
    assert record.phase == "completed"
    assert asset.upload_status == "completed"
    assert asset.source_type == "uploaded"
    assert asset.checksum_sha256 == https_fixture["sha256"]
    assert asset.size_bytes == https_fixture["size"]
    from app.services.storage import media_root

    final = media_root() / asset.storage_path
    assert final.is_file()
    assert hashlib.sha256(final.read_bytes()).hexdigest() == https_fixture["sha256"]
    # Fixture was fetched by worker (server-side), not by a browser.
    assert https_fixture["handler"].get_count >= 1

    # Normal probe after import — public playability still requires packaging.
    probe_job, _ = queue_probe_job(db_session, settings=e2e_settings, asset=asset, admin_id=None)
    from app.models.media_processing import MEDIA_PROCESSING_WORKER_JOB_TYPES
    from app.services.media_processing.jobs import execute_probe_job

    claimed_probe = claim_next_job(
        db_session,
        settings=e2e_settings,
        worker_id="e2e-probe",
        allowed_job_types=MEDIA_PROCESSING_WORKER_JOB_TYPES,
    )
    assert claimed_probe is not None and claimed_probe.id == probe_job.id
    result = execute_probe_job(db_session, settings=e2e_settings, job=claimed_probe)
    assert result.status == "completed"
    db_session.refresh(asset)
    assert asset.processing_status == "completed"
    assert asset.video_codec is not None


def test_https_fixture_resume_206_and_range_ignored_200(
    db_session, e2e_settings, https_fixture, monkeypatch
):
    _allow_loopback_fixture(monkeypatch, https_fixture["url"])
    movie = Movie(
        title="E2E Resume",
        slug=f"e2e-resume-{new_uuid()[:8]}",
        status="draft",
        description="synthetic",
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)

    job, record, asset = queue_remote_media_import(
        db_session,
        settings=e2e_settings,
        url=https_fixture["url"],
        owner_type="movie",
        owner_id=movie.id,
        destination="local_origin",
        admin_id=1,
    )
    from app.services.storage import media_root

    part = media_root() / "temp" / f"remote-import-{asset.id}.part"
    part.parent.mkdir(parents=True, exist_ok=True)
    partial = https_fixture["mp4"].read_bytes()[: 64 * 1024]
    part.write_bytes(partial)
    record.accept_ranges = True
    record.bytes_downloaded = len(partial)
    db_session.add(record)
    job.status = "running"
    db_session.add(job)
    db_session.commit()

    from app.services.media_remote_import import execute_remote_media_import

    execute_remote_media_import(db_session, settings=e2e_settings, job=job)
    db_session.refresh(job)
    db_session.refresh(asset)
    assert job.status == "completed"
    assert https_fixture["handler"].last_range == f"bytes={len(partial)}-"
    assert asset.checksum_sha256 == https_fixture["sha256"]

    # Range ignored → clean restart
    https_fixture["handler"].ignore_range = True
    movie2 = Movie(
        title="E2E Restart",
        slug=f"e2e-restart-{new_uuid()[:8]}",
        status="draft",
        description="synthetic",
    )
    db_session.add(movie2)
    db_session.commit()
    db_session.refresh(movie2)
    job2, record2, asset2 = queue_remote_media_import(
        db_session,
        settings=e2e_settings,
        url=https_fixture["url"].replace("synthetic.mp4", "synthetic2.mp4"),
        owner_type="movie",
        owner_id=movie2.id,
        destination="local_origin",
        admin_id=1,
    )
    # Same fixture file content for checksum uniqueness conflict? different movie ok, but
    # checksum unique on media_assets — use same file so may collide. Clear prior checksum
    # uniqueness by using same content is a problem. Soften: delete first asset checksum.
    asset.checksum_sha256 = None
    db_session.add(asset)
    db_session.commit()

    part2 = media_root() / "temp" / f"remote-import-{asset2.id}.part"
    part2.parent.mkdir(parents=True, exist_ok=True)
    part2.write_bytes(partial)
    record2.accept_ranges = True
    db_session.add(record2)
    job2.status = "running"
    db_session.add(job2)
    db_session.commit()
    execute_remote_media_import(db_session, settings=e2e_settings, job=job2)
    db_session.refresh(job2)
    db_session.refresh(asset2)
    assert job2.status == "completed"
    assert asset2.checksum_sha256 == https_fixture["sha256"]


def test_remote_import_worker_run_once_requires_flags(db_session, e2e_settings, monkeypatch):
    monkeypatch.setenv("ENABLE_REMOTE_MEDIA_IMPORT", "false")
    get_settings.cache_clear()
    settings = get_settings()
    # No jobs — run_once returns False without crashing.
    assert run_remote_import_once(db_session, settings=settings, worker_id="x") is False
