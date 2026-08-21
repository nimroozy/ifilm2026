"""Isolated ASGI application factory for the branch-cache HTTP service candidate.

Not mounted in the central FastAPI app. Not activated by production compose.
Intended for TestClient / explicit development lab only.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging_filters import RequestLoggingMiddleware, install_token_redaction_logging
from app.core.security_headers import SecurityHeadersMiddleware
from app.services.branch_cache.data_plane.cache_store import CacheStore
from app.services.branch_cache.data_plane.engine import BranchDataPlaneEngine
from app.services.branch_cache.service.config import (
    BranchServiceConfig,
    BranchServiceConfigError,
    validate_branch_service_config,
)
from app.services.branch_cache.service.http_adapt import new_request_id, safe_error_envelope
from app.services.branch_cache.service.routes import build_router
from app.services.branch_cache.service.state import BranchServiceState


class _MethodAllowlistMiddleware(BaseHTTPMiddleware):
    _ALLOWED = frozenset({"GET", "HEAD"})

    async def dispatch(self, request: Request, call_next):
        # Allow metrics/health through GET/HEAD only; reject others early.
        if request.method not in self._ALLOWED and not request.url.path.startswith("/v1/obj/"):
            # Object routes have their own 405 handlers for write methods.
            if request.url.path in {"/health", "/ready", "/metrics"}:
                return safe_error_envelope(
                    status_code=405, code="method_not_allowed", request_id=new_request_id()
                )
        return await call_next(request)


class _NoDirectoryListingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.endswith("/") and path not in {"/"}:
            return safe_error_envelope(
                status_code=404, code="not_found", request_id=new_request_id()
            )
        return await call_next(request)


def create_branch_cache_app(cfg: BranchServiceConfig) -> FastAPI:
    """Build an isolated branch-cache ASGI app. Raises on unsafe config."""
    validate_branch_service_config(cfg)

    # Engine requires Phase 4 sim flags for serve(); enforce in lab settings.
    if not cfg.settings.enable_branch_cache_data_plane_sim:
        raise BranchServiceConfigError(
            "branch HTTP service requires ENABLE_BRANCH_CACHE_DATA_PLANE_SIM in lab settings",
            code="sim_required",
        )
    if not cfg.settings.enable_branch_cache_local_serve:
        raise BranchServiceConfigError(
            "branch HTTP service requires ENABLE_BRANCH_CACHE_LOCAL_SERVE",
            code="local_serve_required",
        )

    cfg.cache_root.mkdir(parents=True, exist_ok=True)
    cache = CacheStore(
        cfg.cache_root,
        node_id=cfg.node_id,
        high_watermark_bytes=cfg.high_watermark_bytes,
        low_watermark_bytes=cfg.low_watermark_bytes,
        min_free_bytes=cfg.min_free_bytes,
    )
    engine = BranchDataPlaneEngine(
        node_id=cfg.node_id,
        site_id=cfg.site_id,
        cache=cache,
        origin=cfg.origin,
        public_key_pem=cfg.public_key_pem,
        settings=cfg.settings,
        max_concurrent_fills=cfg.max_concurrent_fills,
    )
    state = BranchServiceState()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        install_token_redaction_logging()
        yield
        state.start_shutdown()

    app = FastAPI(
        title="iFilm Branch Cache (lab candidate)",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.branch_cfg = cfg
    app.state.branch_engine = engine
    app.state.branch_state = state

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware, logger_name="app.branch_cache.access")
    app.add_middleware(_NoDirectoryListingMiddleware)
    app.add_middleware(_MethodAllowlistMiddleware)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, __: Exception) -> JSONResponse:
        # Never leak tracebacks/provider errors.
        return safe_error_envelope(
            status_code=500, code="internal_error", request_id=new_request_id()
        )

    app.include_router(build_router(engine=engine, cfg=cfg, state=state))
    return app
