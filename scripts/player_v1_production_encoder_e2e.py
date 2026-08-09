#!/usr/bin/env python3
"""E2E: admin multi-track workflow → production encoder → EXT-X-MEDIA master.

Creates primary video + FA/PS dubbed audio + EN/FA/PS subs, configures media_tracks,
runs the real media-processing worker encode_hls path, and verifies the generated
master playlist (no hand-edited manifests).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "backend"))

REPORT = Path("/opt/cursor/artifacts/pr62-production-encoder-e2e.json")


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[:2000])


def _mp4(path: Path, *, duration: float = 3.0, freq: int = 440) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s=640x360:d={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=f={freq}:d={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ]
    )


def _audio(path: Path, *, duration: float = 3.0, freq: int = 660) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=f={freq}:d={duration}",
            "-c:a",
            "aac",
            str(path),
        ]
    )


def _vtt(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n{text}\n", encoding="utf-8")


def main() -> int:
    os.environ.setdefault("ENABLE_MEDIA_PROCESSING", "true")
    os.environ.setdefault("ENABLE_HLS_ENCODING", "true")
    media_root = Path(tempfile.mkdtemp(prefix="ifilm-prod-encoder-"))
    os.environ["MEDIA_ROOT"] = str(media_root)

    from app.core.config import get_settings
    from app.db.session import SessionLocal
    from app.models.media_assets import MediaAsset, new_uuid
    from app.models.media_tracks import MediaTrack
    from app.services.media_processing.encode_job import queue_encode_hls_job
    from app.services.media_processing.worker import run_once
    from app.services.storage import (
        asset_storage_path,
        ensure_media_layout,
        relative_media_path,
    )

    get_settings.cache_clear()
    settings = get_settings()
    ensure_media_layout()

    db = SessionLocal()
    checks: list[dict] = []

    def ok(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": passed, "detail": detail})
        print(("PASS" if passed else "FAIL"), name, detail)

    try:
        duration = 3.0
        primary_id = new_uuid()
        primary_path = asset_storage_path(
            category="originals", asset_id=primary_id, stored_filename=f"{primary_id}.mp4"
        )
        _mp4(primary_path, duration=duration, freq=440)
        primary = MediaAsset(
            id=primary_id,
            original_filename="primary.mp4",
            stored_filename=f"{primary_id}.mp4",
            mime_type="video/mp4",
            extension="mp4",
            size_bytes=primary_path.stat().st_size,
            width=640,
            height=360,
            duration_seconds=duration,
            video_codec="h264",
            audio_codec="aac",
            audio_stream_count=1,
            video_frame_rate=25.0,
            storage_backend="local",
            storage_path=relative_media_path(primary_path),
            category="originals",
            upload_status="completed",
            processing_status="none",
            probed_at=datetime.now(UTC),
            probe_version="ffprobe-json-v1",
            probe_json={},
        )
        db.add(primary)

        def add_audio(lang: str, freq: int) -> MediaAsset:
            aid = new_uuid()
            path = asset_storage_path(category="audio", asset_id=aid, stored_filename=f"{aid}.m4a")
            _audio(path, duration=duration, freq=freq)
            asset = MediaAsset(
                id=aid,
                original_filename=f"{lang}.m4a",
                stored_filename=f"{aid}.m4a",
                mime_type="audio/mp4",
                extension="m4a",
                size_bytes=path.stat().st_size,
                duration_seconds=duration,
                audio_codec="aac",
                audio_stream_count=1,
                storage_backend="local",
                storage_path=relative_media_path(path),
                category="audio",
                upload_status="completed",
                processing_status="completed",
                probed_at=datetime.now(UTC),
                probe_version="ffprobe-json-v1",
                probe_json={},
            )
            db.add(asset)
            return asset

        def add_sub(lang: str, text: str) -> MediaAsset:
            aid = new_uuid()
            path = asset_storage_path(category="subtitles", asset_id=aid, stored_filename=f"{aid}.vtt")
            _vtt(path, text)
            asset = MediaAsset(
                id=aid,
                original_filename=f"{lang}.vtt",
                stored_filename=f"{aid}.vtt",
                mime_type="text/vtt",
                extension="vtt",
                size_bytes=path.stat().st_size,
                duration_seconds=duration,
                audio_stream_count=0,
                storage_backend="local",
                storage_path=relative_media_path(path),
                category="subtitles",
                upload_status="completed",
                processing_status="completed",
                probed_at=datetime.now(UTC),
                probe_version="ffprobe-json-v1",
                probe_json={},
            )
            db.add(asset)
            return asset

        fa = add_audio("fa", 550)
        ps = add_audio("ps", 660)
        en_sub = add_sub("en", "Hello")
        fa_sub = add_sub("fa", "سلام")
        ps_sub = add_sub("ps", "سلام")
        db.flush()

        db.add_all(
            [
                MediaTrack(
                    media_asset_id=primary.id,
                    track_type="audio",
                    language_code="en",
                    is_default=True,
                    is_dubbed=False,
                    source_stream_index=0,
                    sort_order=0,
                ),
                MediaTrack(
                    media_asset_id=primary.id,
                    track_type="audio",
                    language_code="fa",
                    is_default=False,
                    is_dubbed=True,
                    source_media_asset_id=fa.id,
                    sort_order=1,
                ),
                MediaTrack(
                    media_asset_id=primary.id,
                    track_type="audio",
                    language_code="ps",
                    is_default=False,
                    is_dubbed=True,
                    source_media_asset_id=ps.id,
                    sort_order=2,
                ),
                MediaTrack(
                    media_asset_id=primary.id,
                    track_type="subtitle",
                    language_code="en",
                    source_media_asset_id=en_sub.id,
                    sort_order=0,
                ),
                MediaTrack(
                    media_asset_id=primary.id,
                    track_type="subtitle",
                    language_code="fa",
                    source_media_asset_id=fa_sub.id,
                    sort_order=1,
                ),
                MediaTrack(
                    media_asset_id=primary.id,
                    track_type="subtitle",
                    language_code="ps",
                    source_media_asset_id=ps_sub.id,
                    sort_order=2,
                ),
            ]
        )
        db.commit()
        db.refresh(primary)

        job, package, created = queue_encode_hls_job(
            db, settings=settings, asset=primary, admin_id=None
        )
        ok("queue_encode", created and job.status == "queued", job.id)
        ran = run_once(db, settings=settings, worker_id="prod-encoder-e2e")
        db.refresh(job)
        db.refresh(package)
        ok("worker_completed", ran and job.status == "completed", f"{job.error_code}:{job.error_message}")
        ok("package_active", package.is_active is True and package.status == "completed")

        master = Path(settings.media_root) / package.master_playlist_path
        text = master.read_text(encoding="utf-8")
        ok("has_ext_x_media_audio", "#EXT-X-MEDIA:TYPE=AUDIO" in text)
        ok("has_ext_x_media_subs", "#EXT-X-MEDIA:TYPE=SUBTITLES" in text)
        ok("single_default", text.count("DEFAULT=YES") == 1)
        ok("fa_name", "فارسی دوبله" in text)
        ok("ps_name", "پښتو دوبله" in text)
        ok("audio_labels", all(x in text for x in ("audio_en/", "audio_fa/", "audio_ps/")))
        ok("sub_labels", all(x in text for x in ("subs_en/", "subs_fa/", "subs_ps/")))
        ok("no_storage_leak", "packages/" not in text and "/tmp/" not in text)

        report = {
            "ok": all(c["ok"] for c in checks),
            "checks": checks,
            "master_excerpt": text[:1200],
            "package_id": package.id,
            "media_root": str(media_root),
            "strategy": (
                "video-only ABR ladder + alternate AAC audio HLS + WebVTT subtitle HLS; "
                "one master with EXT-X-MEDIA groups"
            ),
        }
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print("Wrote", REPORT)
        return 0 if report["ok"] else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
