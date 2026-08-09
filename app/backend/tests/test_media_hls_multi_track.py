"""Production multi-audio / subtitle HLS packaging via the real encoder."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.models.media_assets import MediaAsset, new_uuid
from app.models.media_tracks import MediaTrack
from app.services.media_processing.encode_job import queue_encode_hls_job
from app.services.media_processing.playlists import MediaGroupRef, VariantRef, build_master_playlist
from app.services.media_processing.track_packaging import duration_mismatch
from app.services.media_processing.worker import run_once
from app.services.storage import (
    asset_storage_path,
    ensure_media_layout,
    media_root,
    relative_media_path,
)


def _mp4(path: Path, *, size: str = "640x360", duration: float = 2.0, freq: int = 440) -> None:
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
            f"sine=f={freq}:d={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def _audio_mp4(path: Path, *, duration: float = 2.0, freq: int = 660) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
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
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def _vtt(path: Path, *, text: str = "Hello") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:01.500\n" + text + "\n",
        encoding="utf-8",
    )


def _asset(
    db_session,
    *,
    category: str,
    filename: str,
    maker,
    duration: float = 2.0,
    width: int | None = 640,
    height: int | None = 360,
    audio_stream_count: int = 1,
) -> MediaAsset:
    ensure_media_layout()
    asset_id = new_uuid()
    stored = f"{asset_id}{Path(filename).suffix}"
    dest = asset_storage_path(category=category, asset_id=asset_id, stored_filename=stored)
    maker(dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    asset = MediaAsset(
        id=asset_id,
        original_filename=filename,
        stored_filename=stored,
        mime_type="video/mp4" if category != "subtitles" else "text/vtt",
        extension=Path(filename).suffix.lstrip("."),
        size_bytes=dest.stat().st_size,
        checksum_sha256=digest,
        width=width,
        height=height,
        duration_seconds=duration,
        video_codec="h264" if category == "originals" else None,
        audio_codec="aac" if audio_stream_count else None,
        audio_stream_count=audio_stream_count,
        video_frame_rate=25.0 if category == "originals" else None,
        storage_backend="local",
        storage_path=relative_media_path(dest),
        category=category,
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


def test_duration_mismatch_blocks_packaging():
    assert duration_mismatch(primary_seconds=100, track_seconds=90, tolerance_seconds=2) is not None
    assert duration_mismatch(primary_seconds=100, track_seconds=101, tolerance_seconds=2) is None


def test_master_playlist_emits_ext_x_media():
    text = build_master_playlist(
        [
            VariantRef(
                label="240p",
                bandwidth=400000,
                width=426,
                height=240,
                playlist_rel="240p/index.m3u8",
                audio_group="audio",
                subtitles_group="subs",
            )
        ],
        media_groups=[
            MediaGroupRef(
                media_type="AUDIO",
                group_id="audio",
                name="English",
                language="en",
                playlist_rel="audio_en/index.m3u8",
                is_default=True,
            ),
            MediaGroupRef(
                media_type="AUDIO",
                group_id="audio",
                name="فارسی دوبله",
                language="fa",
                playlist_rel="audio_fa/index.m3u8",
            ),
            MediaGroupRef(
                media_type="SUBTITLES",
                group_id="subs",
                name="English",
                language="en",
                playlist_rel="subs_en/index.m3u8",
            ),
        ],
    )
    assert "#EXT-X-MEDIA:TYPE=AUDIO" in text
    assert 'LANGUAGE="fa"' in text
    assert "فارسی دوبله" in text
    assert 'AUDIO="audio"' in text
    assert 'SUBTITLES="subs"' in text
    assert text.count("DEFAULT=YES") == 1


def test_worker_multi_track_package_emits_ext_x_media(db_session):
    settings = get_settings()
    primary = _asset(
        db_session,
        category="originals",
        filename="primary.mp4",
        maker=lambda p: _mp4(p, duration=2.0, freq=440),
        duration=2.0,
    )
    fa_audio = _asset(
        db_session,
        category="audio",
        filename="fa.m4a",
        maker=lambda p: _audio_mp4(p, duration=2.0, freq=550),
        duration=2.0,
        width=None,
        height=None,
    )
    ps_audio = _asset(
        db_session,
        category="audio",
        filename="ps.m4a",
        maker=lambda p: _audio_mp4(p, duration=2.0, freq=660),
        duration=2.0,
        width=None,
        height=None,
    )
    en_sub = _asset(
        db_session,
        category="subtitles",
        filename="en.vtt",
        maker=lambda p: _vtt(p, text="Hello"),
        duration=2.0,
        width=None,
        height=None,
        audio_stream_count=0,
    )
    fa_sub = _asset(
        db_session,
        category="subtitles",
        filename="fa.vtt",
        maker=lambda p: _vtt(p, text="سلام"),
        duration=2.0,
        width=None,
        height=None,
        audio_stream_count=0,
    )
    ps_sub = _asset(
        db_session,
        category="subtitles",
        filename="ps.vtt",
        maker=lambda p: _vtt(p, text="سلام پښتو"),
        duration=2.0,
        width=None,
        height=None,
        audio_stream_count=0,
    )

    db_session.add_all(
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
                source_media_asset_id=fa_audio.id,
                sort_order=1,
            ),
            MediaTrack(
                media_asset_id=primary.id,
                track_type="audio",
                language_code="ps",
                is_default=False,
                is_dubbed=True,
                source_media_asset_id=ps_audio.id,
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
    db_session.commit()

    job, package, created = queue_encode_hls_job(
        db_session, settings=settings, asset=primary, admin_id=None
    )
    assert created is True
    assert run_once(db_session, settings=settings, worker_id="hls-multi") is True
    db_session.refresh(job)
    db_session.refresh(package)
    assert job.status == "completed", (job.error_code, job.error_message)
    assert package.status == "completed"
    assert package.is_active is True

    master = media_root() / package.master_playlist_path
    text = master.read_text(encoding="utf-8")
    assert "#EXT-X-MEDIA:TYPE=AUDIO" in text
    assert "#EXT-X-MEDIA:TYPE=SUBTITLES" in text
    assert 'LANGUAGE="en"' in text
    assert 'LANGUAGE="fa"' in text
    assert 'LANGUAGE="ps"' in text
    assert "فارسی دوبله" in text
    assert "پښتو دوبله" in text
    assert text.count("DEFAULT=YES") == 1
    assert "audio_en/index.m3u8" in text
    assert "audio_fa/index.m3u8" in text
    assert "audio_ps/index.m3u8" in text
    assert "subs_fa/index.m3u8" in text
    labels = sorted(r.label for r in package.renditions)
    assert "audio_en" in labels
    assert "audio_fa" in labels
    assert "subs_en" in labels
    # Single-track muxed packages never emit EXT-X-MEDIA — this one must.
    assert "packages/" not in text
