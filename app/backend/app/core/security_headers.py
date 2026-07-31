"""ASGI middleware that applies Content-Security-Policy and related headers."""

from __future__ import annotations

from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import get_settings
from app.core.csp import CspMode, security_header_map


def resolve_csp_mode() -> CspMode:
    settings = get_settings()
    if settings.csp_mode in {"production", "development"}:
        return settings.csp_mode  # type: ignore[return-value]
    if settings.app_env in {"production", "staging"}:
        return "production"
    return "development"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Authoritative CSP + baseline security headers for all HTTP responses."""

    def __init__(self, app: ASGIApp, mode: CspMode | None = None):
        super().__init__(app)
        self._fixed_mode = mode

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        mode = self._fixed_mode or resolve_csp_mode()
        for key, value in security_header_map(mode=mode).items():
            # Do not overwrite a more specific CSP set by a route.
            if key == "Content-Security-Policy" and key in response.headers:
                continue
            response.headers[key] = value
        return response
