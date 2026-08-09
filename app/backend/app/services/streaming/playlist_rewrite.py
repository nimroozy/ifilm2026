"""In-memory HLS playlist rewriting onto protected token routes."""

from __future__ import annotations

import re

_URI_LINE = re.compile(r"^(?!#)(.+)$")
# Rewrite relative playlist URIs inside EXT-X-MEDIA attributes.
_MEDIA_URI = re.compile(
    r'(URI=")((?:(?!\.\.)[^"/])+)/([^"/]+\.m3u8)(")',
    re.IGNORECASE,
)


def rewrite_master_playlist(text: str, *, stream_base: str) -> str:
    """Rewrite variant and EXT-X-MEDIA playlist URIs onto `{stream_base}/…`."""
    base = stream_base.rstrip("/")
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            out.append(line.rstrip("\n"))
            continue
        if stripped.startswith("#"):
            if stripped.upper().startswith("#EXT-X-MEDIA:") and "URI=" in stripped.upper():

                def _rewrite_media_uri(match: re.Match[str]) -> str:
                    label = match.group(2)
                    return f'{match.group(1)}{base}/{label}/index.m3u8{match.group(4)}'

                out.append(_MEDIA_URI.sub(_rewrite_media_uri, stripped))
            else:
                out.append(line.rstrip("\n"))
            continue
        # Stored masters use `{label}/index.m3u8` (relative).
        name = stripped.split("?")[0].lstrip("./")
        if "/" in name:
            label, rest = name.split("/", 1)
            if rest.endswith(".m3u8"):
                out.append(f"{base}/{label}/index.m3u8")
                continue
        if name.endswith(".m3u8"):
            label = name[: -len(".m3u8")]
            out.append(f"{base}/{label}/index.m3u8")
            continue
        out.append(f"{base}/{name}")
    return "\n".join(out) + "\n"


def rewrite_variant_playlist(text: str, *, stream_base: str, label: str) -> str:
    """Rewrite segment URIs to `{stream_base}/{label}/{segment}`."""
    base = stream_base.rstrip("/")
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out.append(line.rstrip("\n"))
            continue
        name = stripped.split("?")[0].lstrip("./")
        # Reject absolute or parent references in stored playlists.
        if name.startswith("/") or ".." in name.split("/"):
            continue
        segment = name.split("/")[-1]
        out.append(f"{base}/{label}/{segment}")
    return "\n".join(out) + "\n"
