"""Deliver rewritten playlists and ranged segments for an authorized session."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.media_encoding import MediaPackage
from app.models.media_playback import MediaPlaybackSession
from app.services.object_storage.origin_read import (
    fetch_package_object_bytes,
    logical_master_relative,
    logical_segment_relative,
    logical_variant_relative,
    origin_hls_read_fallback_enabled,
    package_allows_origin_read,
)
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

_LOCAL_MISS = frozenset({"package_missing", "not_found"})


def _gone(exc: SessionGoneError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={"code": exc.code, "message": str(exc)},
    )


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


def _read_playlist_text(
    package: MediaPackage,
    *,
    resolve_local,
    logical_relative: str,
    settings: Settings,
) -> str:
    try:
        path = resolve_local()
        return path.read_text(encoding="utf-8", errors="replace")
    except StreamPathError as exc:
        if (
            exc.code in _LOCAL_MISS
            and origin_hls_read_fallback_enabled(settings)
            and package_allows_origin_read(package)
        ):
            data = fetch_package_object_bytes(package, logical_relative, settings=settings)
            return data.decode("utf-8", errors="replace")
        raise


def _read_segment_bytes(
    package: MediaPackage,
    *,
    label: str,
    segment_name: str,
    settings: Settings,
) -> tuple[bytes, str]:
    try:
        path = resolve_segment(package, label, segment_name)
        media_type = "text/vtt" if path.suffix.lower() == ".vtt" else "video/mp2t"
        return path.read_bytes(), media_type
    except StreamPathError as exc:
        if (
            exc.code in _LOCAL_MISS
            and origin_hls_read_fallback_enabled(settings)
            and package_allows_origin_read(package)
        ):
            rel = logical_segment_relative(label, segment_name)
            data = fetch_package_object_bytes(package, rel, settings=settings)
            media_type = "text/vtt" if segment_name.lower().endswith(".vtt") else "video/mp2t"
            return data, media_type
        raise


def deliver_master(db: Session, token: str, request: Request) -> Response:
    settings = get_settings()
    session = authorize_stream_session(db, token, settings)
    package = session.media_package
    try:
        text = _read_playlist_text(
            package,
            resolve_local=lambda: resolve_master_playlist(package),
            logical_relative=logical_master_relative(),
            settings=settings,
        )
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
        text = _read_playlist_text(
            package,
            resolve_local=lambda: resolve_variant_playlist(package, label),
            logical_relative=logical_variant_relative(label),
            settings=settings,
        )
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

    local_path: Path | None = None
    data: bytes | None = None
    try:
        local_path = resolve_segment(package, label, segment_name)
        media_type = "text/vtt" if local_path.suffix.lower() == ".vtt" else "video/mp2t"
        file_size = local_path.stat().st_size
    except StreamPathError as exc:
        if (
            exc.code in _LOCAL_MISS
            and origin_hls_read_fallback_enabled(settings)
            and package_allows_origin_read(package)
        ):
            try:
                data, media_type = _read_segment_bytes(
                    package, label=label, segment_name=segment_name, settings=settings
                )
            except StreamPathError as inner:
                raise _path_http(inner) from inner
            file_size = len(data)
        else:
            raise _path_http(exc) from exc

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

    if local_path is not None:
        if byte_range is None:
            payload = local_path.read_bytes()
            headers = {**SEGMENT_HEADERS, "Content-Length": str(len(payload))}
            return Response(content=payload, media_type=media_type, headers=headers, status_code=200)
        with local_path.open("rb") as handle:
            handle.seek(byte_range.start)
            payload = handle.read(byte_range.length)
        headers = {
            **SEGMENT_HEADERS,
            "Content-Length": str(len(payload)),
            "Content-Range": f"bytes {byte_range.start}-{byte_range.end}/{file_size}",
        }
        return Response(content=payload, media_type=media_type, headers=headers, status_code=206)

    assert data is not None
    if byte_range is None:
        headers = {**SEGMENT_HEADERS, "Content-Length": str(len(data))}
        return Response(content=data, media_type=media_type, headers=headers, status_code=200)
    sliced = data[byte_range.start : byte_range.end + 1]
    headers = {
        **SEGMENT_HEADERS,
        "Content-Length": str(len(sliced)),
        "Content-Range": f"bytes {byte_range.start}-{byte_range.end}/{file_size}",
    }
    return Response(content=sliced, media_type=media_type, headers=headers, status_code=206)


def read_file_unchanged(path: Path) -> bytes:
    """Helper for tests: confirm on-disk playlists are not mutated."""
    return path.read_bytes()
