"""Immutable / versioned object-key conventions for media objects.

Keys are relative to a configured prefix (default ``ifilm``). They mirror the
existing MEDIA_ROOT layout so local and remote backends stay interchangeable.

Version segment ``v1`` is part of the key so future layout changes can coexist
without rewriting historical objects.
"""

from __future__ import annotations

import re
from enum import StrEnum

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


class StorageObjectKind(StrEnum):
    ORIGINAL = "originals"
    PACKAGE = "packages"
    POSTER = "posters"
    BACKDROP = "backdrops"
    LOGO = "logos"
    STILL = "stills"
    TRAILER = "trailers"
    SUBTITLE = "subtitles"
    AUDIO = "audio"
    TEMP = "temp"


ARTWORK_KIND_MAP = {
    "poster": StorageObjectKind.POSTER,
    "backdrop": StorageObjectKind.BACKDROP,
    "logo": StorageObjectKind.LOGO,
    "still": StorageObjectKind.STILL,
    "trailer": StorageObjectKind.TRAILER,
}


def _require_safe(segment: str, *, field: str) -> str:
    value = (segment or "").strip()
    if not value or not _SAFE_SEGMENT.match(value):
        raise ValueError(f"Unsafe or empty {field} for object key")
    if value in {".", ".."}:
        raise ValueError(f"Unsafe {field} for object key")
    return value


class ObjectKeyBuilder:
    """Build versioned object keys for originals, packages, artwork, and trailers."""

    def __init__(self, *, prefix: str = "ifilm", layout_version: str = "v1") -> None:
        self.prefix = _require_safe(prefix or "ifilm", field="prefix")
        self.layout_version = _require_safe(layout_version or "v1", field="layout_version")

    def _join(self, *parts: str) -> str:
        return "/".join(parts)

    def original_key(self, *, asset_id: str, stored_filename: str) -> str:
        return self._join(
            self.prefix,
            self.layout_version,
            StorageObjectKind.ORIGINAL.value,
            _require_safe(asset_id, field="asset_id"),
            _require_safe(stored_filename, field="stored_filename"),
        )

    def package_root(self, *, asset_id: str, package_id: str) -> str:
        """Prefix for an immutable HLS package tree (no trailing slash)."""
        return self._join(
            self.prefix,
            self.layout_version,
            StorageObjectKind.PACKAGE.value,
            _require_safe(asset_id, field="asset_id"),
            _require_safe(package_id, field="package_id"),
        )

    def package_object_key(self, *, asset_id: str, package_id: str, relative_path: str) -> str:
        """Key for a file inside a package (e.g. ``master.m3u8``, ``720p/seg_000.ts``)."""
        rel = (relative_path or "").replace("\\", "/").strip().lstrip("/")
        if not rel or ".." in rel.split("/"):
            raise ValueError("Unsafe package relative_path")
        for part in rel.split("/"):
            _require_safe(part, field="package_path_segment")
        return f"{self.package_root(asset_id=asset_id, package_id=package_id)}/{rel}"

    def artwork_key(self, *, kind: StorageObjectKind, asset_id: str, stored_filename: str) -> str:
        if kind not in {
            StorageObjectKind.POSTER,
            StorageObjectKind.BACKDROP,
            StorageObjectKind.LOGO,
            StorageObjectKind.STILL,
            StorageObjectKind.TRAILER,
        }:
            raise ValueError(f"Unsupported artwork kind: {kind}")
        return self._join(
            self.prefix,
            self.layout_version,
            kind.value,
            _require_safe(asset_id, field="asset_id"),
            _require_safe(stored_filename, field="stored_filename"),
        )

    def artwork_relative_key(self, *, relative_path: str) -> str:
        """Map an ARTWORK_ROOT-relative path to an immutable object key.

        Example: ``posters/tmdb-poster-1-abc.jpg`` → ``ifilm/v1/posters/tmdb-poster-1-abc.jpg``
        (asset_id omitted; filename is already unique / content-addressed).
        """
        rel = (relative_path or "").replace("\\", "/").strip().lstrip("/")
        if not rel or ".." in rel.split("/"):
            raise ValueError("Unsafe artwork relative_path")
        parts = rel.split("/")
        if len(parts) != 2:
            raise ValueError("Artwork relative_path must be {kind_dir}/{filename}")
        kind_dir, filename = parts
        kind = next((k for k in ARTWORK_KIND_MAP.values() if k.value == kind_dir), None)
        if kind is None:
            raise ValueError(f"Unsupported artwork directory: {kind_dir}")
        return self._join(
            self.prefix,
            self.layout_version,
            kind.value,
            _require_safe(filename, field="stored_filename"),
        )

    def sidecar_key(
        self,
        *,
        kind: StorageObjectKind,
        asset_id: str,
        stored_filename: str,
    ) -> str:
        if kind not in {StorageObjectKind.SUBTITLE, StorageObjectKind.AUDIO}:
            raise ValueError(f"Unsupported sidecar kind: {kind}")
        return self._join(
            self.prefix,
            self.layout_version,
            kind.value,
            _require_safe(asset_id, field="asset_id"),
            _require_safe(stored_filename, field="stored_filename"),
        )
