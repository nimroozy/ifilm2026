"""Deliver rewritten playlists and ranged segments for an authorized session."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.media_playback import MediaPlaybackSession
from app.services.streaming.audit import record_session_event
from app.services.streaming.paths import (
    StreamPathError,
    resolve_master_playlist,
    resolve_segment,
    resolve_variant_playlist,
)
from app.services.streaming.playlist_rewrite import (
    rewrite_master_playlist,
    rewrite_variant_playlist,
)
from app.services.streaming.range import RangeError, parse_byte_range
from app.services.streaming.sessions import (
    SessionGoneError,
    lookup_session_by_token,
    stream_base_path,
    touch_session_access,
)

PLAYLIST_HEADERS = {
    "Cache-Control": "private, no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}
SEGMENT_HEADERS = {
    "Cache-Control": "private, no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Accept-Ranges": "bytes",
}


def _gone(exc: SessionGoneError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc))


def _path_http(exc: StreamPathError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND
    if exc.code in {"traversal_rejected", "escape_rejected", "symlink_rejected", "outside_packages"}:
        code = status.HTTP_400_BAD_REQUEST
    if exc.code in {"invalid_label", "invalid_segment", "unsupported_extension"}:
        code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail="Stream path rejected")


def authorize_stream_session(db: Session, token: str, settings: Settings | None = None) -> MediaPlaybackSession:
    try:
        return lookup_session_by_token(db, token, settings=settings)
    except SessionGoneError as exc:
        raise _gone(exc) from exc


def deliver_master(db: Session, token: str, request: Request) -> Response:
    settings = get_settings()
    session = authorize_stream_session(db, token, settings)
    package = session.media_package
    try:
        path = resolve_master_playlist(package)
        text = path.read_text(encoding="utf-8", errors="replace")
    except StreamPathError as exc:
        raise _path_http(exc) from exc
    base = stream_base_path(api_prefix=settings.api_prefix, token=token)
    body = rewrite_master_playlist(text, stream_base=base)
    touch_session_access(db, session, settings=settings)
    record_session_event(
        "playback_master_served",
        session_id=session.id,
        media_asset_id=session.media_asset_id,
        media_package_id=session.media_package_id,
    )
    return Response(
        content=body,
        media_type="application/vnd.apple.mpegurl",
        headers=PLAYLIST_HEADERS,
    )


def deliver_variant(db: Session, token: str, label: str, request: Request) -> Response:
    settings = get_settings()
    session = authorize_stream_session(db, token, settings)
    package = session.media_package
    try:
        path = resolve_variant_playlist(package, label)
        text = path.read_text(encoding="utf-8", errors="replace")
    except StreamPathError as exc:
        raise _path_http(exc) from exc
    base = stream_base_path(api_prefix=settings.api_prefix, token=token)
    body = rewrite_variant_playlist(text, stream_base=base, label=label)
    touch_session_access(db, session, settings=settings)
    return Response(
        content=body,
        media_type="application/vnd.apple.mpegurl",
        headers=PLAYLIST_HEADERS,
    )


def deliver_segment(
    db: Session, token: str, label: str, segment_name: str, request: Request
) -> FastAPIResponse:
    settings = get_settings()
    session = authorize_stream_session(db, token, settings)
    package = session.media_package
    try:
        path = resolve_segment(package, label, segment_name)
    except StreamPathError as exc:
        raise _path_http(exc) from exc

    file_size = path.stat().st_size
    range_header = request.headers.get("range")
    try:
        byte_range = parse_byte_range(range_header, file_size=file_size)
    except RangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            detail="Invalid range",
            headers={"Content-Range": f"bytes */{file_size}"},
        ) from exc

    touch_session_access(db, session, settings=settings)

    if byte_range is None:
        data = path.read_bytes()
        headers = {**SEGMENT_HEADERS, "Content-Length": str(len(data))}
        return Response(content=data, media_type="video/mp2t", headers=headers, status_code=200)

    with path.open("rb") as handle:
        handle.seek(byte_range.start)
        data = handle.read(byte_range.length)
    headers = {
        **SEGMENT_HEADERS,
        "Content-Length": str(len(data)),
        "Content-Range": f"bytes {byte_range.start}-{byte_range.end}/{file_size}",
    }
    return Response(content=data, media_type="video/mp2t", headers=headers, status_code=206)


def read_file_unchanged(path: Path) -> bytes:
    """Helper for tests: confirm on-disk playlists are not mutated."""
    return path.read_bytes()
