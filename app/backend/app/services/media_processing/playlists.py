"""HLS master and variant playlist helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MediaGroupRef:
    """Alternate audio or subtitle rendition for #EXT-X-MEDIA."""

    media_type: str  # AUDIO | SUBTITLES
    group_id: str
    name: str
    language: str
    playlist_rel: str
    is_default: bool = False
    autoselect: bool = True
    forced: bool = False


@dataclass(frozen=True)
class VariantRef:
    label: str
    bandwidth: int
    width: int
    height: int
    playlist_rel: str
    codecs: str = "avc1.4d401f,mp4a.40.2"
    audio_group: str | None = None
    subtitles_group: str | None = None


def build_master_playlist(
    variants: list[VariantRef],
    *,
    media_groups: list[MediaGroupRef] | None = None,
) -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:4" if media_groups else "#EXT-X-VERSION:3"]
    for media in media_groups or []:
        attrs = [
            f"TYPE={media.media_type}",
            f'GROUP-ID="{media.group_id}"',
            f'NAME="{media.name}"',
            f'LANGUAGE="{media.language}"',
            f"DEFAULT={'YES' if media.is_default else 'NO'}",
            f"AUTOSELECT={'YES' if media.autoselect else 'NO'}",
        ]
        if media.media_type == "SUBTITLES":
            attrs.append(f"FORCED={'YES' if media.forced else 'NO'}")
        attrs.append(f'URI="{media.playlist_rel}"')
        lines.append("#EXT-X-MEDIA:" + ",".join(attrs))
    for variant in variants:
        stream = (
            "#EXT-X-STREAM-INF:"
            f"BANDWIDTH={variant.bandwidth},"
            f"RESOLUTION={variant.width}x{variant.height},"
            f'CODECS="{variant.codecs}"'
        )
        if variant.audio_group:
            stream += f',AUDIO="{variant.audio_group}"'
        if variant.subtitles_group:
            stream += f',SUBTITLES="{variant.subtitles_group}"'
        lines.append(stream)
        lines.append(variant.playlist_rel)
    return "\n".join(lines) + "\n"


def write_master_playlist(
    path: Path,
    variants: list[VariantRef],
    *,
    media_groups: list[MediaGroupRef] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        build_master_playlist(variants, media_groups=media_groups),
        encoding="utf-8",
    )


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
