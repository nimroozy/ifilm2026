from pathlib import Path

from app.core.config import get_settings

MEDIA_SUBDIRS = ("originals", "posters", "backdrops", "trailers", "subtitles", "temp", "packages")


def media_root() -> Path:
    root = Path(get_settings().media_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def artwork_root() -> Path:
    """Dedicated public artwork tree — never packages/originals/temp."""
    root = Path(get_settings().artwork_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_artwork_layout() -> Path:
    root = artwork_root()
    for name in ("posters", "backdrops", "logos", "stills"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def ensure_media_layout() -> Path:
    """Create the configured local media directory tree."""
    root = media_root()
    for name in MEDIA_SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def upload_dir() -> Path:
    """Legacy upload_jobs destination (kept for existing routes)."""
    path = media_root() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def packages_dir(*, create: bool = True) -> Path:
    path = media_root() / "packages"
    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Read-only package mounts (API) must still resolve the path.
            if not path.exists():
                raise
    return path


def packages_work_dir() -> Path:
    path = packages_dir(create=True) / "work"
    path.mkdir(parents=True, exist_ok=True)
    return path


def hls_dir() -> Path:
    path = media_root() / "hls"
    path.mkdir(parents=True, exist_ok=True)
    return path


def media_category_dir(category: str) -> Path:
    ensure_media_layout()
    normalized = category.strip().lower()
    allowed = {"originals", "posters", "backdrops", "trailers", "subtitles"}
    if normalized not in allowed:
        raise ValueError(f"Unknown media category: {category}")
    path = media_root() / normalized
    path.mkdir(parents=True, exist_ok=True)
    return path


def temp_upload_dir() -> Path:
    path = media_root() / "temp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def asset_storage_path(*, category: str, asset_id: str, stored_filename: str) -> Path:
    """Absolute path under MEDIA_ROOT/<category>/<asset_id>/<stored_filename>."""
    dest_dir = media_category_dir(category) / asset_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir / stored_filename


def relative_media_path(absolute: Path) -> str:
    """Store paths relative to MEDIA_ROOT when possible."""
    root = media_root()
    resolved = absolute.resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)
