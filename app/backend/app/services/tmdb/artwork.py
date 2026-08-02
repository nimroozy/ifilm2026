"""Safe TMDB artwork download and local storage."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import Settings

APPROVED_IMAGE_HOSTS = {"image.tmdb.org"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
KIND_DIRS = {
    "poster": "posters",
    "backdrop": "backdrops",
    "logo": "logos",
    "still": "stills",
}
MIME_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class ArtworkError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredArtwork:
    url: str
    relative_path: str
    checksum_sha256: str
    size_bytes: int
    width: int | None = None
    height: int | None = None


def _public_artwork_url(relative_path: str) -> str:
    base = (os.environ.get("DEMO_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if base:
        return f"{base}/artwork/{relative_path}"
    return f"/artwork/{relative_path}"


def _allowed_hosts(tmdb_configuration: dict[str, Any] | None = None) -> set[str]:
    hosts = set(APPROVED_IMAGE_HOSTS)
    images = (tmdb_configuration or {}).get("images") if isinstance(tmdb_configuration, dict) else None
    if isinstance(images, dict):
        for key in ("secure_base_url", "base_url"):
            value = images.get(key)
            if isinstance(value, str):
                host = urlparse(value).hostname
                if host:
                    hosts.add(host.lower())
    return hosts


def validate_artwork_url(url: str, *, tmdb_configuration: dict[str, Any] | None = None) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ArtworkError("Artwork URL must be HTTPS")
    if parsed.hostname.lower() not in _allowed_hosts(tmdb_configuration):
        raise ArtworkError("Rejected non-TMDB artwork host")
    if ".." in parsed.path or "\\" in parsed.path:
        raise ArtworkError("Rejected artwork path traversal")
    return url


def build_image_url(settings: Settings, path: str, *, size: str = "original") -> str:
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    base = settings.tmdb_image_base_url.rstrip("/") + "/"
    return urljoin(base, f"{size.strip('/')}{path}")


def _dimensions_with_pillow(data: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001 - Pillow is optional in backend requirements.
        return None, None
    with Image.open(BytesIO(data)) as image:
        width, height = image.size
        image.verify()
    if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
        raise ArtworkError("Artwork dimensions exceed safety limits")
    return int(width), int(height)


def _validate_image_bytes(data: bytes, content_type: str) -> tuple[str, int | None, int | None]:
    if not data:
        raise ArtworkError("Artwork response was empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise ArtworkError("Artwork exceeds maximum size")
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime not in MIME_EXT:
        raise ArtworkError("Unsupported artwork MIME type")
    detected = ""
    if data.startswith(b"\xff\xd8\xff"):
        detected = "jpg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "png"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        detected = "webp"
    if detected not in {"jpg", "png", "webp"}:
        raise ArtworkError("Artwork bytes are not a supported image")
    ext = MIME_EXT[mime]
    if detected != ext:
        raise ArtworkError("Artwork MIME type does not match bytes")
    width, height = _dimensions_with_pillow(data)
    return ext, width, height


def store_artwork_bytes(
    settings: Settings,
    data: bytes,
    *,
    kind: str,
    tmdb_id: int,
    content_type: str,
) -> StoredArtwork:
    if kind not in KIND_DIRS:
        raise ArtworkError(f"Unsupported artwork kind: {kind}")
    ext, width, height = _validate_image_bytes(data, content_type)
    checksum = hashlib.sha256(data).hexdigest()
    filename = f"tmdb-{kind}-{int(tmdb_id)}-{checksum[:12]}.{ext}"
    relative_path = f"{KIND_DIRS[kind]}/{filename}"
    root = Path(settings.artwork_root).resolve()
    for dirname in KIND_DIRS.values():
        (root / dirname).mkdir(parents=True, exist_ok=True)
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ArtworkError("Artwork destination escaped artwork root") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return StoredArtwork(
        url=_public_artwork_url(relative_path),
        relative_path=relative_path,
        checksum_sha256=checksum,
        size_bytes=len(data),
        width=width,
        height=height,
    )


def download_artwork(
    settings: Settings,
    url: str,
    *,
    kind: str,
    tmdb_id: int,
    tmdb_configuration: dict[str, Any] | None = None,
    http_client: httpx.Client | None = None,
) -> StoredArtwork:
    url = validate_artwork_url(url, tmdb_configuration=tmdb_configuration)
    close_client = False
    client = http_client
    if client is None:
        client = httpx.Client(timeout=float(settings.tmdb_request_timeout_seconds))
        close_client = True
    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    raise ArtworkError("Artwork exceeds maximum size")
                chunks.append(chunk)
            data = b"".join(chunks)
    except ArtworkError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ArtworkError(f"Artwork download failed: {exc}") from exc
    finally:
        if close_client:
            client.close()
    return store_artwork_bytes(settings, data, kind=kind, tmdb_id=tmdb_id, content_type=content_type)
