"""Upload path validation helpers."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from fastapi import HTTPException, status

SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._ -]+$")


def sanitize_upload_filename(filename: str | None) -> str:
    if not filename or not filename.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    name = filename.strip().replace("\\", "/")
    if "/" in name or name in {".", ".."} or ".." in name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    pure = PurePosixPath(name)
    if pure.is_absolute() or len(pure.parts) != 1 or pure.parts[0] in {"", ".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    if not SAFE_FILENAME_RE.match(pure.name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    return pure.name


def validate_upload_content_type(content_type: str | None, allowed: list[str]) -> str:
    normalized = (content_type or "").split(";")[0].strip().lower()
    if not normalized or normalized not in {item.lower() for item in allowed}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid media type")
    return normalized
