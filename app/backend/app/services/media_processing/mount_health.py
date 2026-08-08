"""Startup / Docker health checks for shared MEDIA_ROOT upload mounts.

Production compose bind-mounts each upload category onto the worker. When a
category volume is omitted, ``ensure_media_layout`` can create an empty
container-local directory that looks present but is not the shared volume —
probe then fails with "Uploaded media file is missing".

This module verifies required category paths exist, are readable, and (in
container / production layouts) are real mounts — without creating missing
directories.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Categories the API can finalize uploads into; worker must share each mount.
REQUIRED_MEDIA_MOUNT_CATEGORIES = (
    "originals",
    "trailers",
    "subtitles",
    "posters",
    "backdrops",
)

MountStatusCode = Literal[
    "ok",
    "missing",
    "not_directory",
    "not_mounted",
    "unreadable",
]


class MediaMountHealthError(RuntimeError):
    """Required MEDIA_ROOT category mount(s) missing or not a shared volume."""

    def __init__(self, message: str, *, missing: list[str]):
        super().__init__(message)
        self.missing = list(missing)


@dataclass(frozen=True)
class CategoryMountStatus:
    category: str
    path: Path
    exists: bool
    is_directory: bool
    is_mount: bool
    readable: bool
    status: MountStatusCode
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class MediaMountHealth:
    media_root: Path
    require_mounts: bool
    categories: tuple[CategoryMountStatus, ...]
    missing: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.missing

    def public_mounts(self) -> dict[str, MountStatusCode]:
        """Category → status codes only (no host paths / volume names)."""
        return {item.category: item.status for item in self.categories}

    def public_report(self) -> dict[str, Any]:
        return {
            "media_processing_ready": self.ok,
            "mounts": self.public_mounts(),
        }


def mounts_required(settings: Settings | None = None) -> bool:
    """Whether category paths must be Docker/volume mount points.

    Enabled for production/staging, inside Docker, or when explicitly requested.
    Local pytest (APP_ENV=test, no /.dockerenv) only requires readable directories.
    """
    settings = settings or get_settings()
    explicit = os.environ.get("MEDIA_REQUIRE_CATEGORY_MOUNTS", "").strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        return True
    if explicit in {"0", "false", "no", "off"}:
        return False
    if settings.app_env in {"production", "staging", "prod"}:
        return True
    return Path("/.dockerenv").exists()


def _path_readable(path: Path) -> bool:
    """True when the process can list/read the directory (shared volume access)."""
    try:
        if not os.access(path, os.R_OK | os.X_OK):
            return False
        # Force a real read against the mount (catches some stale/broken binds).
        os.listdir(path)
        return True
    except OSError:
        return False


def _category_status(
    root: Path, category: str, *, require_mounts: bool
) -> CategoryMountStatus:
    path = root / category
    exists = path.exists()
    is_directory = path.is_dir() if exists else False
    is_mount = False
    readable = False

    if is_directory:
        try:
            is_mount = bool(path.is_mount() or root.is_mount())
        except OSError:
            is_mount = False
        readable = _path_readable(path)

    if not exists:
        status: MountStatusCode = "missing"
        detail = f"{path} is missing (volume mount not configured)"
    elif not is_directory:
        status = "not_directory"
        detail = f"{path} exists but is not a directory"
    elif require_mounts and not is_mount:
        status = "not_mounted"
        detail = (
            f"{path} exists but is not a valid shared media mount "
            "(container-local empty directory; shared volume missing)"
        )
    elif not readable:
        status = "unreadable"
        detail = f"{path} exists but is not readable by the worker"
    else:
        status = "ok"
        detail = "ok"

    return CategoryMountStatus(
        category=category,
        path=path,
        exists=exists,
        is_directory=is_directory,
        is_mount=is_mount,
        readable=readable,
        status=status,
        detail=detail,
    )


def inspect_media_mount_health(settings: Settings | None = None) -> MediaMountHealth:
    """Inspect required upload category paths under MEDIA_ROOT (no mkdir)."""
    settings = settings or get_settings()
    root = Path(settings.media_root)
    require = mounts_required(settings)
    categories = tuple(
        _category_status(root, category, require_mounts=require)
        for category in REQUIRED_MEDIA_MOUNT_CATEGORIES
    )
    missing = tuple(item.category for item in categories if not item.ok)
    return MediaMountHealth(
        media_root=root,
        require_mounts=require,
        categories=categories,
        missing=missing,
    )


def format_media_mount_health_error(health: MediaMountHealth) -> str:
    lines = [
        "MEDIA MOUNT CHECK FAILED",
        "",
        "Media processing worker unhealthy: required MEDIA_ROOT category "
        "mount(s) unavailable.",
        f"Failed categories: {', '.join(health.missing)}",
        "",
    ]
    for item in health.categories:
        if not item.ok:
            lines.append(item.detail)
    lines.extend(
        [
            "",
            "Worker will exit non-zero and will not consume jobs until mounts match "
            "backend-api upload locations "
            "(originals, trailers, subtitles, posters, backdrops).",
        ]
    )
    return "\n".join(lines)


def assert_required_media_mounts(settings: Settings | None = None) -> MediaMountHealth:
    """Raise MediaMountHealthError when required category mounts are missing."""
    health = inspect_media_mount_health(settings)
    if not health.ok:
        raise MediaMountHealthError(
            format_media_mount_health_error(health),
            missing=list(health.missing),
        )
    return health


def log_media_mount_health(health: MediaMountHealth) -> None:
    if health.ok:
        mode = "mount-required" if health.require_mounts else "directory-only"
        logger.info(
            "Media mount health OK (%s) categories=%s",
            mode,
            ",".join(REQUIRED_MEDIA_MOUNT_CATEGORIES),
        )
        return
    logger.error("%s", format_media_mount_health_error(health))


def worker_media_mounts_healthy(settings: Settings | None = None) -> bool:
    """Return True when required media category mounts are usable."""
    return inspect_media_mount_health(settings).ok


def media_processing_readiness(settings: Settings | None = None) -> dict[str, Any]:
    """Public readiness payload (no host paths / secrets / volume names)."""
    return inspect_media_mount_health(settings).public_report()
