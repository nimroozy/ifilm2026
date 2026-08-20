"""Adapt DataPlaneResponse to Starlette/FastAPI responses."""

from __future__ import annotations

import uuid

from fastapi import Response
from fastapi.responses import JSONResponse
from fastapi.responses import Response as FastAPIResponse

from app.services.branch_cache.data_plane.engine import DataPlaneResponse


def new_request_id() -> str:
    return uuid.uuid4().hex


def safe_error_envelope(
    *,
    status_code: int,
    code: str,
    request_id: str,
) -> JSONResponse:
    """Generic error body — no provider/filesystem/token details."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "request_id": request_id}},
        headers={
            "X-Request-Id": request_id,
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def adapt_data_plane_response(
    dp: DataPlaneResponse,
    *,
    method: str,
    request_id: str,
) -> Response:
    headers = dict(dp.headers)
    headers["X-Request-Id"] = request_id
    headers.setdefault("X-Content-Type-Options", "nosniff")
    # Immutable package objects may be cached privately at the edge briefly;
    # playlists stay no-store via engine.
    if dp.decision.fallback_to_central or dp.status_code >= 400:
        # Map engine fallback/errors to safe envelopes when body empty.
        if not dp.body and dp.status_code >= 400:
            code = dp.decision.decision
            return safe_error_envelope(status_code=dp.status_code, code=code, request_id=request_id)

    body = b"" if method.upper() == "HEAD" else dp.body
    # Content-Length must reflect full representation size for HEAD of 200,
    # or range length for 206.
    headers["Content-Length"] = str(dp.content_length if method.upper() == "HEAD" else len(body))
    if method.upper() == "HEAD":
        # For HEAD, content_length on dp is already the would-be body length.
        headers["Content-Length"] = str(dp.content_length)

    return FastAPIResponse(
        content=body,
        status_code=dp.status_code,
        media_type=dp.content_type,
        headers=headers,
    )
