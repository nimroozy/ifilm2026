"""Request path redaction so playback tokens never appear in application logs."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# /api/stream/{opaque_token}/... (path token; query handled separately)
_STREAM_TOKEN_RE = re.compile(
    r"(?P<prefix>/api/stream/)(?P<token>[A-Za-z0-9_-]{16,128})(?P<suffix>/|\?|$)"
)

# Query / form keys that must never appear in logs.
_SECRET_QUERY_KEYS = frozenset(
    {
        "token",
        "expires",
        "access_token",
        "refresh_token",
        "playback_token",
        "signature",
        "sig",
        "authorization",
        "api_key",
        "apikey",
        "tmdb_api_key",
        "password",
        "secret",
        "client_secret",
    }
)

_BEARER_RE = re.compile(r"(?i)(authorization:\s*bearer\s+)(\S+)")
# Common credential assignment fragments in free-text log lines.
_CRED_ASSIGN_RE = re.compile(
    r"(?i)\b(api[_-]?key|tmdb[_-]?api[_-]?key|jwt_secret|playback_token_secret|"
    r"postgres_password|redis_password|client_secret)\s*[=:]\s*([^\s&,;]+)"
)


def redact_secret_query(url_or_qs: str) -> str:
    """Redact secret-bearing query parameters in a URL or raw query string."""
    if not url_or_qs:
        return url_or_qs
    if "://" in url_or_qs or url_or_qs.startswith("/"):
        parts = urlsplit(url_or_qs)
        if not parts.query:
            return url_or_qs
        redacted = [
            (k, "[REDACTED]" if k.lower() in _SECRET_QUERY_KEYS else v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
        ]
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(redacted), parts.fragment)
        )
    # Raw query string
    if "=" not in url_or_qs:
        return url_or_qs
    redacted = [
        (k, "[REDACTED]" if k.lower() in _SECRET_QUERY_KEYS else v)
        for k, v in parse_qsl(url_or_qs, keep_blank_values=True)
    ]
    return urlencode(redacted)


def redact_stream_path(path: str) -> str:
    """Redact stream path tokens and secret query params from a path or URL-like string."""
    if not path:
        return path
    redacted = _BEARER_RE.sub(r"\1[REDACTED]", path)
    redacted = _CRED_ASSIGN_RE.sub(r"\1=[REDACTED]", redacted)
    redacted = _STREAM_TOKEN_RE.sub(r"\g<prefix>[REDACTED]\g<suffix>", redacted)
    # Only treat as URL/query when clearly path- or URL-shaped (avoid mangling free text).
    if "?" in redacted or "://" in redacted or redacted.startswith("/"):
        # Query redaction only when a query string is present.
        if "?" in redacted or "://" in redacted:
            redacted = redact_secret_query(redacted)
    return redacted


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
        # path only (Starlette) — also redact query if middleware logs full URL later
        path = redact_stream_path(request.url.path)
        query = redact_secret_query(request.url.query) if request.url.query else ""
        target = f"{path}?{query}" if query else path
        self.logger.info(
            "%s %s %s",
            request.method,
            target,
            response.status_code,
        )
        return response
