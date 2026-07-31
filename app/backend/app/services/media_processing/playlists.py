"""HLS master and variant playlist helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VariantRef:
    label: str
    bandwidth: int
    width: int
    height: int
    playlist_rel: str
    codecs: str = "avc1.4d401f,mp4a.40.2"


def build_master_playlist(variants: list[VariantRef]) -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for variant in variants:
        lines.append(
            "#EXT-X-STREAM-INF:"
            f"BANDWIDTH={variant.bandwidth},"
            f"RESOLUTION={variant.width}x{variant.height},"
            f'CODECS="{variant.codecs}"'
        )
        lines.append(variant.playlist_rel)
    return "\n".join(lines) + "\n"


def write_master_playlist(path: Path, variants: list[VariantRef]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_master_playlist(variants), encoding="utf-8")


def count_media_segments(playlist_text: str) -> int:
    count = 0
    for line in playlist_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        count += 1
    return count


def listed_segment_names(playlist_text: str) -> list[str]:
    names: list[str] = []
    for line in playlist_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        names.append(stripped.split("?")[0])
    return names
