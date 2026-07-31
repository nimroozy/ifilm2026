"""Validate HLS package output before atomic promotion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.media_processing.errors import PackageValidationError
from app.services.media_processing.playlists import count_media_segments, listed_segment_names


@dataclass(frozen=True)
class ValidatedRendition:
    label: str
    height: int
    width: int
    playlist_path: Path
    segment_count: int
    bandwidth: int


def validate_hls_package(
    package_root: Path,
    *,
    expected_labels: list[str],
    source_height: int,
    rendition_heights: dict[str, int],
    rendition_widths: dict[str, int],
    rendition_bandwidths: dict[str, int],
) -> tuple[Path, list[ValidatedRendition]]:
    master = package_root / "master.m3u8"
    if not master.is_file():
        raise PackageValidationError("Missing master.m3u8")
    master_text = master.read_text(encoding="utf-8", errors="replace")
    if "#EXTM3U" not in master_text:
        raise PackageValidationError("Invalid master playlist header")
    if "#EXT-X-STREAM-INF" not in master_text:
        raise PackageValidationError("Master playlist has no variants")

    validated: list[ValidatedRendition] = []
    for label in expected_labels:
        height = rendition_heights[label]
        if height > source_height:
            raise PackageValidationError(
                f"Rendition {label} height {height} exceeds source {source_height}"
            )
        playlist = package_root / label / "index.m3u8"
        if not playlist.is_file():
            raise PackageValidationError(f"Missing variant playlist for {label}")
        text = playlist.read_text(encoding="utf-8", errors="replace")
        if "#EXTM3U" not in text:
            raise PackageValidationError(f"Invalid variant playlist for {label}")
        if "#EXT-X-ENDLIST" not in text:
            raise PackageValidationError(f"Variant playlist for {label} is not a complete VOD")
        segments = listed_segment_names(text)
        if not segments:
            raise PackageValidationError(f"Variant playlist for {label} has no segments")
        for name in segments:
            seg_path = playlist.parent / name
            if not seg_path.is_file() or seg_path.stat().st_size <= 0:
                raise PackageValidationError(f"Missing or empty segment {name} for {label}")
        # Ensure master references this variant.
        rel = f"{label}/index.m3u8"
        if rel not in master_text:
            raise PackageValidationError(f"Master playlist missing {rel}")
        validated.append(
            ValidatedRendition(
                label=label,
                height=height,
                width=rendition_widths[label],
                playlist_path=playlist,
                segment_count=count_media_segments(text),
                bandwidth=rendition_bandwidths[label],
            )
        )
    return master, validated
