from pathlib import Path

from app.core.config import get_settings


def media_root() -> Path:
    root = Path(get_settings().media_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def upload_dir() -> Path:
    path = media_root() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def hls_dir() -> Path:
    path = media_root() / "hls"
    path.mkdir(parents=True, exist_ok=True)
    return path
