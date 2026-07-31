"""Secure resolution of files inside an active HLS package directory."""

from __future__ import annotations

import re
from pathlib import Path

from app.models.media_encoding import MediaPackage
from app.services.media_processing.errors import PathSecurityError
from app.services.storage import media_root, packages_dir

_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.ts$")
ALLOWED_PLAYLIST_NAMES = frozenset({"master.m3u8", "index.m3u8"})


class StreamPathError(Exception):
    def __init__(self, code: str, message: str = "Invalid stream path"):
        self.code = code
        super().__init__(message)


def package_root_dir(package: MediaPackage) -> Path:
    """Absolute directory for a completed package; rejects escapes and workspaces."""
    if package.status != "completed" or not package.is_active:
        raise StreamPathError("package_not_active", "Package is not active")
    if not package.storage_path:
        raise StreamPathError("package_path_missing", "Package storage path missing")

    root = media_root().resolve()
    packages = packages_dir(create=False).resolve()
    raw = Path(package.storage_path)
    if raw.is_absolute():
        raise StreamPathError("absolute_path_rejected", "Absolute package paths are not allowed")
    parts = raw.parts
    if ".." in parts or any(part.startswith("/") for part in parts):
        raise StreamPathError("traversal_rejected", "Path traversal rejected")
    if parts and parts[0] != "packages":
        raise StreamPathError("outside_packages", "Package must live under packages/")
    if "work" in parts:
        raise StreamPathError("workspace_rejected", "Encode workspaces are not streamable")

    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(packages)
    except ValueError as exc:
        raise StreamPathError("outside_packages", "Package escapes packages root") from exc
    if not candidate.is_dir():
        raise StreamPathError("package_missing", "Package directory not found")
    if candidate.is_symlink():
        raise StreamPathError("symlink_rejected", "Package root must not be a symlink")
    return candidate


def _reject_symlink(path: Path, package_root: Path) -> Path:
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        raise StreamPathError("resolve_failed", "Unable to resolve path") from exc
    try:
        resolved.relative_to(package_root.resolve())
    except ValueError as exc:
        raise StreamPathError("escape_rejected", "Path escapes package root") from exc

    # Walk each component and reject symlinks that leave the package.
    current = package_root
    try:
        rel = resolved.relative_to(package_root.resolve())
    except ValueError as exc:
        raise StreamPathError("escape_rejected", "Path escapes package root") from exc
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            link_target = current.resolve()
            try:
                link_target.relative_to(package_root.resolve())
            except ValueError as exc:
                raise StreamPathError("symlink_rejected", "Symlink escapes package root") from exc
    if not resolved.is_file():
        raise StreamPathError("not_found", "Stream file not found")
    return resolved


def resolve_master_playlist(package: MediaPackage) -> Path:
    root = package_root_dir(package)
    return _reject_symlink(root / "master.m3u8", root)


def resolve_variant_playlist(package: MediaPackage, label: str) -> Path:
    if not _LABEL_RE.fullmatch(label):
        raise StreamPathError("invalid_label", "Invalid rendition label")
    root = package_root_dir(package)
    # Ensure rendition belongs to this package record when labels are known.
    known = {item.label for item in (package.renditions or [])}
    if known and label not in known:
        raise StreamPathError("unknown_rendition", "Rendition not part of this package")
    return _reject_symlink(root / label / "index.m3u8", root)


def resolve_segment(package: MediaPackage, label: str, segment_name: str) -> Path:
    if not _LABEL_RE.fullmatch(label):
        raise StreamPathError("invalid_label", "Invalid rendition label")
    if not _SEGMENT_RE.fullmatch(segment_name):
        raise StreamPathError("invalid_segment", "Unsupported or invalid segment name")
    if segment_name.lower().endswith((".m3u8", ".mp4", ".mkv", ".mov")):
        raise StreamPathError("unsupported_extension", "Unsupported stream extension")
    root = package_root_dir(package)
    known = {item.label for item in (package.renditions or [])}
    if known and label not in known:
        raise StreamPathError("unknown_rendition", "Rendition not part of this package")
    return _reject_symlink(root / label / segment_name, root)


def assert_under_artwork_root(path: Path, artwork_root: Path) -> Path:
    """Resolve a path under artwork root; reject symlink escapes."""
    root = artwork_root.resolve()
    try:
        resolved = path.resolve()
    except OSError as exc:
        raise PathSecurityError("Unable to resolve artwork path") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PathSecurityError("Artwork path escapes ARTWORK_ROOT") from exc
    current = root
    try:
        rel = resolved.relative_to(root)
    except ValueError as exc:
        raise PathSecurityError("Artwork path escapes ARTWORK_ROOT") from exc
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            target = current.resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise PathSecurityError("Artwork symlink escapes ARTWORK_ROOT") from exc
    if not resolved.is_file():
        raise PathSecurityError("Artwork file not found")
    # Must never resolve into MEDIA_ROOT packages/originals via trickery —
    # artwork_root must be configured separately from media packages.
    return resolved
