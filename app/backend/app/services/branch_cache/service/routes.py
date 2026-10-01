"""HTTP routes for the isolated branch-cache service candidate."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse

from app.services.branch_cache import metrics
from app.services.branch_cache.data_plane.engine import BranchDataPlaneEngine
from app.services.branch_cache.data_plane.keys import normalize_relative_path
from app.services.branch_cache.ops.metrics_export import render_prometheus_text, snapshot_for_export
from app.services.branch_cache.service.config import BranchServiceConfig
from app.services.branch_cache.service.http_adapt import (
    adapt_data_plane_response,
    new_request_id,
    safe_error_envelope,
)
from app.services.branch_cache.service.state import BranchServiceState


def build_router(
    *,
    engine: BranchDataPlaneEngine,
    cfg: BranchServiceConfig,
    state: BranchServiceState,
) -> APIRouter:
    router = APIRouter()

    @router.api_route("/health", methods=["GET", "HEAD"])
    def health(request: Request) -> Response:
        if not cfg.enable_health:
            return safe_error_envelope(
                status_code=404, code="not_found", request_id=new_request_id()
            )
        rid = new_request_id()
        headers = {"X-Request-Id": rid, "Cache-Control": "no-store"}
        if request.method.upper() == "HEAD":
            return Response(status_code=200, headers=headers)
        return JSONResponse(
            {"status": "ok", "service": "branch-cache", "request_id": rid},
            headers=headers,
        )

    @router.api_route("/ready", methods=["GET", "HEAD"])
    def ready(request: Request) -> Response:
        if not cfg.enable_ready:
            return safe_error_envelope(
                status_code=404, code="not_found", request_id=new_request_id()
            )
        rid = new_request_id()
        snap = state.snapshot()
        ok = not snap["shutting_down"] and cfg.cache_root is not None
        if cfg.runtime_mode != "node":
            ok = ok and bool(cfg.public_key_pem)
        headers = {"X-Request-Id": rid, "Cache-Control": "no-store"}
        if request.method.upper() == "HEAD":
            return Response(status_code=200 if ok else 503, headers=headers)
        payload = {
            "ready": ok,
            "draining": snap["draining"],
            "live_origin": cfg.runtime_mode == "node",
            "client_redirect": False,
            "edge_grant_key": bool((cfg.public_key_pem or "").strip()),
            "request_id": rid,
        }
        return JSONResponse(
            payload,
            status_code=200 if ok else 503,
            headers=headers,
        )

    @router.get("/metrics")
    def metrics_endpoint() -> Response:
        if not cfg.enable_metrics:
            return safe_error_envelope(
                status_code=404, code="not_found", request_id=new_request_id()
            )
        rid = new_request_id()
        snap = snapshot_for_export(
            const_labels={"node_role": "branch_lab", "env": cfg.settings.app_env}
        )
        text = render_prometheus_text(snap)
        return Response(
            content=text,
            media_type="text/plain; version=0.0.4",
            headers={"X-Request-Id": rid, "Cache-Control": "no-store"},
        )

    @router.api_route(
        "/v1/obj/{asset_id}/{package_id}/{relative_path:path}",
        methods=["GET", "HEAD"],
    )
    def get_object(
        request: Request,
        asset_id: str,
        package_id: str,
        relative_path: str,
        authorization: str | None = Header(default=None),
        x_ifilm_session_id: str | None = Header(default=None, alias="X-Ifilm-Session-Id"),
        range: str | None = Header(default=None),  # noqa: A002
    ) -> Response:
        rid = new_request_id()
        if not state.begin_request():
            return safe_error_envelope(status_code=503, code="shutting_down", request_id=rid)
        try:
            # Header size budget (approx)
            hdr_bytes = sum(len(k) + len(v) for k, v in request.headers.items())
            if hdr_bytes > cfg.max_header_bytes:
                return safe_error_envelope(
                    status_code=431, code="headers_too_large", request_id=rid
                )
            raw_path = request.url.path
            if len(raw_path) > cfg.max_path_length:
                return safe_error_envelope(status_code=414, code="path_too_long", request_id=rid)
            if ".." in raw_path or "%2e" in raw_path.lower() or "%2f" in raw_path.lower():
                return safe_error_envelope(status_code=400, code="path_rejected", request_id=rid)

            try:
                rel = normalize_relative_path(relative_path)
            except Exception:
                return safe_error_envelope(status_code=400, code="path_rejected", request_id=rid)

            if not authorization or not authorization.lower().startswith("bearer "):
                return safe_error_envelope(status_code=401, code="missing_grant", request_id=rid)
            token = authorization.split(" ", 1)[1].strip()
            if not token or len(token) > 8192:
                return safe_error_envelope(status_code=401, code="invalid_grant", request_id=rid)
            session_id = (x_ifilm_session_id or "").strip()
            if not session_id or len(session_id) > 64:
                return safe_error_envelope(status_code=400, code="missing_session", request_id=rid)
            if not (cfg.public_key_pem or "").strip():
                # CDN-P1 node without edge-grant material: fail closed, never serve.
                return safe_error_envelope(
                    status_code=503, code="edge_grants_not_configured", request_id=rid
                )

            path_prefix = f"/v1/obj/{asset_id}/{package_id}/"
            if state.draining:
                engine.cache.draining = True

            dp = engine.serve(
                grant_token=token,
                asset_id=asset_id,
                package_id=package_id,
                session_id=session_id,
                relative_path=rel,
                path_prefix=path_prefix,
                range_header=range,
                enforce_replay=True,
            )
            return adapt_data_plane_response(dp, method=request.method, request_id=rid)
        finally:
            state.end_request()

    @router.api_route(
        "/v1/obj/{asset_id}/{package_id}/{relative_path:path}",
        methods=["POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    def method_not_allowed(relative_path: str) -> Response:  # noqa: ARG001
        return safe_error_envelope(
            status_code=405, code="method_not_allowed", request_id=new_request_id()
        )

    return router


def public_status(cfg: BranchServiceConfig, state: BranchServiceState) -> dict[str, Any]:
    return {
        "service": "branch-cache",
        "node_id": cfg.node_id,
        "site_id": cfg.site_id,
        "health_enabled": cfg.enable_health,
        "ready_enabled": cfg.enable_ready,
        "metrics_enabled": cfg.enable_metrics,
        "live_origin": False,
        "client_redirect": False,
        "state": state.snapshot(),
        "counters": metrics.snapshot(),
    }
