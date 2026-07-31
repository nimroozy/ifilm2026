"""Safe public artwork serving under ARTWORK_ROOT only (never MEDIA_ROOT)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.services.media_processing.errors import PathSecurityError
from app.services.streaming.paths import assert_under_artwork_root

router = APIRouter(tags=["artwork"])

_ALLOWED_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})


@router.get("/artwork/{path:path}")
def serve_artwork(path: str):
    settings = get_settings()
    root = Path(settings.artwork_root).resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=404, detail="Artwork not found")
    # Reject empty, absolute, or traversal in the request path before join.
    if not path or path.startswith("/") or ".." in Path(path).parts:
        raise HTTPException(status_code=400, detail="Invalid artwork path")
    candidate = root / path
    try:
        resolved = assert_under_artwork_root(candidate, root)
    except PathSecurityError:
        raise HTTPException(status_code=404, detail="Artwork not found") from None
    if resolved.suffix.lower() not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Unsupported artwork type")
    # Ensure resolved path is not under media packages/originals.
    media = Path(settings.media_root).resolve()
    try:
        resolved.relative_to(media)
        raise HTTPException(status_code=404, detail="Artwork not found")
    except ValueError:
        pass
    return FileResponse(resolved)
