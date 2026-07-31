"""Bounded content-signature checks for uploaded media (no external parsers)."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status

# Enough for box headers / magic numbers; never load whole files.
PROBE_BYTES = 64

KIND_MP4 = "mp4"
KIND_MATROSKA = "matroska"
KIND_JPEG = "jpeg"
KIND_PNG = "png"
KIND_WEBP = "webp"
KIND_WEBVTT = "webvtt"
KIND_SRT = "srt"
KIND_ASS = "ass"
KIND_EXECUTABLE = "executable"
KIND_UNKNOWN = "unknown"

EXTENSION_KINDS: dict[str, frozenset[str]] = {
    ".mp4": frozenset({KIND_MP4}),
    ".m4v": frozenset({KIND_MP4}),
    ".mov": frozenset({KIND_MP4}),
    ".qt": frozenset({KIND_MP4}),
    ".mkv": frozenset({KIND_MATROSKA}),
    ".webm": frozenset({KIND_MATROSKA}),
    ".jpg": frozenset({KIND_JPEG}),
    ".jpeg": frozenset({KIND_JPEG}),
    ".png": frozenset({KIND_PNG}),
    ".webp": frozenset({KIND_WEBP}),
    ".vtt": frozenset({KIND_WEBVTT}),
    ".srt": frozenset({KIND_SRT}),
    ".ass": frozenset({KIND_ASS}),
    ".ssa": frozenset({KIND_ASS}),
}

MIME_KINDS: dict[str, frozenset[str]] = {
    "video/mp4": frozenset({KIND_MP4}),
    "video/quicktime": frozenset({KIND_MP4}),
    "video/x-m4v": frozenset({KIND_MP4}),
    "video/x-matroska": frozenset({KIND_MATROSKA}),
    "video/webm": frozenset({KIND_MATROSKA}),
    "video/x-msvideo": frozenset(
        {KIND_UNKNOWN}
    ),  # AVI — accept unknown binary only with matching ext
    "image/jpeg": frozenset({KIND_JPEG}),
    "image/png": frozenset({KIND_PNG}),
    "image/webp": frozenset({KIND_WEBP}),
    "text/vtt": frozenset({KIND_WEBVTT}),
    "application/x-subrip": frozenset({KIND_SRT}),
    "text/plain": frozenset({KIND_SRT, KIND_ASS, KIND_WEBVTT}),
    "text/x-ssa": frozenset({KIND_ASS}),
    "application/octet-stream": frozenset(),  # must be resolved from content + extension
}


@dataclass(frozen=True)
class ContentProbe:
    kind: str
    label: str


def detect_content_kind(prefix: bytes) -> ContentProbe:
    data = prefix or b""
    if len(data) >= 2 and data[:2] == b"MZ":
        return ContentProbe(KIND_EXECUTABLE, "PE/DOS executable")
    if len(data) >= 4 and data[:4] == b"\x7fELF":
        return ContentProbe(KIND_EXECUTABLE, "ELF executable")
    if data.startswith(b"#!"):
        return ContentProbe(KIND_EXECUTABLE, "script shebang")
    if data.startswith(b"%PDF"):
        return ContentProbe(KIND_EXECUTABLE, "PDF (not an allowed media type)")

    # ISO BMFF (MP4/MOV): ....ftyp (box type alone is enough for a bounded probe)
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return ContentProbe(KIND_MP4, "ISO BMFF (MP4/MOV)")

    # Matroska / WebM EBML header
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return ContentProbe(KIND_MATROSKA, "Matroska/WebM")

    if data.startswith(b"\xff\xd8\xff"):
        return ContentProbe(KIND_JPEG, "JPEG")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ContentProbe(KIND_PNG, "PNG")
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ContentProbe(KIND_WEBP, "WebP")

    text = data.lstrip(b"\xef\xbb\xbf")  # UTF-8 BOM
    head = text[:32].decode("utf-8", errors="ignore").lstrip().upper()
    if head.startswith("WEBVTT"):
        return ContentProbe(KIND_WEBVTT, "WebVTT")
    if (
        head.startswith("[SCRIPT INFO]")
        or head.startswith("[V4+ STYLES]")
        or head.startswith("[V4 STYLES]")
    ):
        return ContentProbe(KIND_ASS, "ASS/SSA subtitle")
    # SRT typically starts with a cue index number.
    first_line = text.splitlines()[0].decode("utf-8", errors="ignore").strip() if text else ""
    if first_line.isdigit():
        return ContentProbe(KIND_SRT, "SRT subtitle")

    return ContentProbe(KIND_UNKNOWN, "unknown binary")


def validate_content_compatibility(
    *,
    prefix: bytes,
    extension: str,
    declared_mime: str,
) -> ContentProbe:
    """Ensure prefix signature is allowed and compatible with extension + MIME."""
    probe = detect_content_kind(prefix)
    if probe.kind == KIND_EXECUTABLE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Executable or unsafe content signature detected ({probe.label})",
        )

    ext = (
        extension.lower()
        if extension.startswith(".")
        else f".{extension.lower()}"
        if extension
        else ""
    )
    mime = (declared_mime or "").split(";")[0].strip().lower()

    ext_kinds = EXTENSION_KINDS.get(ext)
    mime_kinds = MIME_KINDS.get(mime)

    if mime == "application/octet-stream":
        if ext_kinds is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="application/octet-stream requires a recognized media extension",
            )
        if probe.kind == KIND_UNKNOWN or probe.kind not in ext_kinds:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content signature does not match the declared file extension",
            )
        return probe

    if mime_kinds is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid media type")

    if ext_kinds is not None and mime_kinds and ext_kinds.isdisjoint(mime_kinds):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MIME type is incompatible with file extension",
        )

    allowed = set(ext_kinds or ()) | set(mime_kinds or ())
    # AVI declared as video/x-msvideo may remain unknown; require non-executable only.
    if mime == "video/x-msvideo":
        if probe.kind == KIND_EXECUTABLE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid media content"
            )
        return probe

    if probe.kind == KIND_UNKNOWN or (allowed and probe.kind not in allowed):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Content signature ({probe.label}) does not match declared "
                f"type ({mime}) / extension ({ext or 'none'})"
            ),
        )
    return probe
