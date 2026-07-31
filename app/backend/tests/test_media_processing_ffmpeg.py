"""FFmpeg process safety and path validation tests."""

from __future__ import annotations

import os
import time

import pytest
from app.models.media_assets import MediaAsset
from app.services.media_processing.errors import (
    PathSecurityError,
    ProbeCancelledError,
    ProbeTimeoutError,
)
from app.services.media_processing.ffmpeg import run_process
from app.services.media_processing.paths import resolve_completed_asset_path
from app.services.storage import media_root


def test_stdout_stderr_truncation():
    # Generate more than 32 bytes of stdout.
    result = run_process(
        ["python3", "-c", "import sys; sys.stdout.write('A'*200); sys.stderr.write('B'*200)"],
        timeout_seconds=5,
        max_stdout_bytes=32,
        max_stderr_bytes=16,
    )
    assert result.returncode == 0
    assert len(result.stdout) == 32
    assert len(result.stderr) == 16
    assert result.truncated_stdout is True
    assert result.truncated_stderr is True


def test_process_timeout():
    with pytest.raises(ProbeTimeoutError):
        run_process(
            ["python3", "-c", "import time; time.sleep(5)"],
            timeout_seconds=0.3,
            max_stdout_bytes=1024,
            max_stderr_bytes=1024,
            poll_interval=0.05,
        )


def test_process_cancellation():
    started = time.monotonic()

    def cancel_after():
        return time.monotonic() - started > 0.2

    with pytest.raises(ProbeCancelledError):
        run_process(
            ["python3", "-c", "import time; time.sleep(5)"],
            timeout_seconds=10,
            max_stdout_bytes=1024,
            max_stderr_bytes=1024,
            cancel_check=cancel_after,
            poll_interval=0.05,
        )


def test_path_traversal_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    media_root()
    outside = tmp_path.parent / "outside-secret.bin"
    outside.write_bytes(b"secret")
    asset = MediaAsset(
        id="a1",
        original_filename="x.mp4",
        stored_filename="x.mp4",
        mime_type="video/mp4",
        upload_status="completed",
        storage_backend="local",
        storage_path="../outside-secret.bin",
        category="originals",
    )
    with pytest.raises(PathSecurityError):
        resolve_completed_asset_path(asset)
    get_settings.cache_clear()
    monkeypatch.delenv("MEDIA_ROOT", raising=False)


def test_symlink_escape_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    from app.core.config import get_settings

    get_settings.cache_clear()
    root = media_root()
    outside = tmp_path / "evil.bin"
    outside.write_bytes(b"evil")
    link = root / "originals" / "escape.mp4"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        link.unlink()
    os.symlink(outside, link)
    asset = MediaAsset(
        id="a2",
        original_filename="escape.mp4",
        stored_filename="escape.mp4",
        mime_type="video/mp4",
        upload_status="completed",
        storage_backend="local",
        storage_path="originals/escape.mp4",
        category="originals",
    )
    with pytest.raises(PathSecurityError):
        resolve_completed_asset_path(asset)
    get_settings.cache_clear()
    monkeypatch.delenv("MEDIA_ROOT", raising=False)
