"""Request path redaction so playback tokens never appear in application logs."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# /api/stream/{opaque_token}/...
_STREAM_TOKEN_RE = re.compile(
    r"(?P<prefix>/api/stream/)(?P<token>[A-Za-z0-9_-]{16,128})(?P<suffix>/|/|$)"
)


def redact_stream_path(path: str) -> str:
    return _STREAM_TOKEN_RE.sub(r"\g<prefix>[REDACTED]\g<suffix>", path)


class TokenRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        redacted = redact_stream_path(msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        if hasattr(record, "path") and isinstance(record.path, str):
            record.path = redact_stream_path(record.path)
        return True


def install_token_redaction_logging() -> None:
    filt = TokenRedactionFilter()
    root = logging.getLogger()
    if not any(isinstance(f, TokenRedactionFilter) for f in root.filters):
        root.addFilter(filt)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "app"):
        log = logging.getLogger(name)
        if not any(isinstance(f, TokenRedactionFilter) for f in log.filters):
            log.addFilter(filt)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit access lines with redacted stream token paths."""

    def __init__(self, app: ASGIApp, logger_name: str = "app.access"):
        super().__init__(app)
        self.logger = logging.getLogger(logger_name)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        path = redact_stream_path(request.url.path)
        self.logger.info(
            "%s %s %s",
            request.method,
            path,
            response.status_code,
        )
        return response
