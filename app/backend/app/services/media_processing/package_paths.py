"""Local package workspace and final promotion paths under MEDIA_ROOT/packages."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.services.media_processing.errors import PathSecurityError
from app.services.storage import media_root, packages_dir, packages_work_dir, relative_media_path


def work_package_dir(job_id: str, *, create: bool = True) -> Path:
    path = packages_work_dir() / job_id
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def final_package_dir(asset_id: str, package_id: str) -> Path:
    path = packages_dir() / asset_id / package_id
    return path


def assert_under_media_root(path: Path) -> Path:
    root = media_root().resolve()
    try:
        resolved = path.resolve()
    except OSError as exc:
        raise PathSecurityError("Unable to resolve package path") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PathSecurityError("Package path escapes MEDIA_ROOT") from exc
    return resolved


def relative_or_raise(path: Path) -> str:
    assert_under_media_root(path)
    return relative_media_path(path)


def remove_tree_if_exists(path: Path | None) -> None:
    if path is None:
        return
    try:
        resolved = assert_under_media_root(path)
    except PathSecurityError:
        return
    if resolved.exists():
        shutil.rmtree(resolved, ignore_errors=True)


def promote_work_to_final(work_dir: Path, final_dir: Path) -> Path:
    """Atomically promote a validated work directory into the final package path."""
    work = assert_under_media_root(work_dir)
    final = assert_under_media_root(final_dir)
    if not work.is_dir():
        raise PathSecurityError("Work package directory missing")
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists():
        # Never clobber a completed package directory in place.
        raise PathSecurityError("Final package path already exists")
    # Same-filesystem rename is atomic for the directory entry.
    work.rename(final)
    return final
