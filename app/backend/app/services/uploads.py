"""Upload path and media type validation helpers."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from fastapi import HTTPException, status

SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._ -]+$")

BLOCKED_EXTENSIONS = frozenset(
    {
        ".exe",
        ".bat",
        ".cmd",
        ".com",
        ".msi",
        ".scr",
        ".ps1",
        ".sh",
        ".bash",
        ".zsh",
        ".php",
        ".phtml",
        ".asp",
        ".aspx",
        ".jsp",
        ".cgi",
        ".dll",
        ".so",
        ".dylib",
        ".jar",
        ".js",
        ".mjs",
        ".vbs",
        ".wsf",
        ".hta",
    }
)

BLOCKED_MIME_TYPES = frozenset(
    {
        "application/x-msdownload",
        "application/x-msdos-program",
        "application/x-executable",
        "application/x-sh",
        "application/x-bat",
        "application/javascript",
        "text/javascript",
        "application/x-httpd-php",
    }
)


def file_extension(filename: str) -> str:
    name = PurePosixPath(filename.replace("\\", "/")).name
    if "." not in name or name.startswith("."):
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


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
    ext = file_extension(pure.name)
    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Executable uploads are not allowed")
    return pure.name


def validate_upload_content_type(content_type: str | None, allowed: list[str]) -> str:
    normalized = (content_type or "").split(";")[0].strip().lower()
    if not normalized or normalized in BLOCKED_MIME_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid media type")
    if normalized not in {item.lower() for item in allowed}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid media type")
    return normalized


def reject_zero_byte_size(size_bytes: int) -> None:
    if size_bytes <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Zero-byte files are not allowed")


def reject_oversized(size_bytes: int, max_bytes: int) -> None:
    if size_bytes < 0 or size_bytes > max_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large")
