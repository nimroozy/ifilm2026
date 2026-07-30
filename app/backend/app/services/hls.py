"""HLS packaging helpers and playlist delivery."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from app.core.config import get_settings
from app.services.storage import hls_dir


DEFAULT_QUALITIES = ["1080p", "720p", "480p", "360p"]


def content_hls_dir(content_type: str, content_id: int, episode_id: int | None = None) -> Path:
    parts = [content_type, str(content_id)]
    if episode_id is not None:
        parts.append(f"ep-{episode_id}")
    path = hls_dir().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def master_playlist_path(content_type: str, content_id: int, episode_id: int | None = None) -> Path:
    return content_hls_dir(content_type, content_id, episode_id) / "master.m3u8"


def public_playlist_url(content_type: str, content_id: int, episode_id: int | None = None) -> str:
    base = get_settings().hls_public_base_url.rstrip("/")
    suffix = f"{content_type}/{content_id}"
    if episode_id is not None:
        suffix = f"{suffix}/ep-{episode_id}"
    return f"{base}/{suffix}/master.m3u8"


def build_master_playlist(qualities: Iterable[str] | None = None) -> str:
    """Generate a placeholder master playlist for foundation/dev without ffmpeg."""
    bandwidth = {
        "1080p": 5_000_000,
        "720p": 2_800_000,
        "480p": 1_400_000,
        "360p": 800_000,
    }
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for quality in qualities or DEFAULT_QUALITIES:
        bw = bandwidth.get(quality, 1_000_000)
        lines.append(f"#EXT-X-STREAM-INF:BANDWIDTH={bw},RESOLUTION={_resolution(quality)}")
        lines.append(f"{quality}/index.m3u8")
    return "\n".join(lines) + "\n"


def _resolution(quality: str) -> str:
    mapping = {
        "1080p": "1920x1080",
        "720p": "1280x720",
        "480p": "854x480",
        "360p": "640x360",
    }
    return mapping.get(quality, "1280x720")


def write_placeholder_package(
    content_type: str,
    content_id: int,
    qualities: List[str] | None = None,
    episode_id: int | None = None,
) -> str:
    root = content_hls_dir(content_type, content_id, episode_id)
    quals = list(qualities or DEFAULT_QUALITIES)
    (root / "master.m3u8").write_text(build_master_playlist(quals), encoding="utf-8")
    for quality in quals:
        qdir = root / quality
        qdir.mkdir(parents=True, exist_ok=True)
        (qdir / "index.m3u8").write_text(
            "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n#EXT-X-MEDIA-SEQUENCE:0\n"
            "#EXTINF:6.0,\nsegment000.ts\n#EXT-X-ENDLIST\n",
            encoding="utf-8",
        )
        (qdir / "segment000.ts").write_bytes(b"\x00" * 16)
    relative = root.relative_to(hls_dir()).as_posix()
    return relative
