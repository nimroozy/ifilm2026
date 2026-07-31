"""Legacy HLS helpers retained only for non-delivery utilities.

Placeholder package writing and public /media/hls delivery were removed in Phase 7.
Protected streaming lives in app.services.streaming.
"""

from __future__ import annotations

from collections.abc import Iterable

DEFAULT_QUALITIES = ["1080p", "720p", "480p", "360p"]


def build_master_playlist(qualities: Iterable[str] | None = None) -> str:
    """Generate a sample master playlist string for unit tests of playlist formatting."""
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
