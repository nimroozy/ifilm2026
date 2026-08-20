"""Admin APIs for branch-cache control plane (Phase 3).

All endpoints require RBAC (cdn.read / cdn.manage). Feature-flag gated.
Never returns private keys, enrollment hashes, Portal/SAS, or customer data.
Enrollment tokens are returned only once at creation/rotation.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.core.deps import DbSession, require_permissions
from app.core.features import require_feature
from app.models.admin import AdminUser
from app.schemas.branch_cache import (
    BranchCacheEdgeGrantIssueIn,
    BranchCacheEdgeGrantVerifyIn,
    BranchCacheHeartbeatIn,
    BranchCacheNodeCreateIn,
    BranchCacheNodeCreateOut,
    BranchCacheNodeOut,
    BranchCacheNodeUpdateIn,
    BranchCacheRouteDryRunIn,
)
from app.services.branch_cache import grants as grant_svc
from app.services.branch_cache import metrics
from app.services.branch_cache import registry as reg
from app.services.branch_cache import routing as route_svc
from app.services.branch_cache.validation import BranchCacheValidationError

router = APIRouter(prefix="/admin/branch-cache", tags=["branch-cache"])


def _require_control_plane() -> None:
    require_feature("enable_branch_cache_control_plane")


def _http_validation(exc: BranchCacheValidationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/status")
def control_plane_status(
    _: Annotated[AdminUser, Depends(require_permissions("cdn.read"))],
) -> dict[str, Any]:
    """Secret-free control-plane status + counters."""
    cfg = get_settings()
    return {
        "enable_branch_cache_control_plane": bool(cfg.enable_branch_cache_control_plane),
        "enable_edge_grant_issue": bool(cfg.enable_edge_grant_issue),
        "enable_branch_cache_shadow_routing": bool(cfg.enable_branch_cache_shadow_routing),
        "enable_branch_cache_data_plane_sim": bool(cfg.enable_branch_cache_data_plane_sim),
        "enable_branch_cache_pull_through": bool(cfg.enable_branch_cache_pull_through),
        "enable_branch_cache_local_serve": bool(cfg.enable_branch_cache_local_serve),
        "enable_branch_cache_pilot_lab": bool(cfg.enable_branch_cache_pilot_lab),
        "edge_grant_configured": bool(
            (cfg.edge_grant_public_key_pem or "").strip() and (cfg.edge_grant_key_id or "").strip()
        ),
        # Never expose whether private key is present beyond a boolean needed for ops.
        "edge_grant_signing_ready": bool((cfg.edge_grant_private_key_pem or "").strip())
        and bool((cfg.edge_grant_public_key_pem or "").strip()),
        "heartbeat_stale_seconds": int(cfg.branch_cache_heartbeat_stale_seconds),
        "min_free_bytes": int(cfg.branch_cache_min_free_bytes),
        "min_protocol_version": cfg.branch_cache_min_protocol_version,
        "legacy_cdn_sync_enabled": bool(cfg.enable_cdn_sync),
        "counters": metrics.snapshot(),
        "data_plane_active": bool(cfg.enable_branch_cache_data_plane_sim),
        "data_plane_mode": "simulation" if cfg.enable_branch_cache_data_plane_sim else "off",
        "client_redirect_active": False,
        "live_http_origin_fetcher": False,
        "live_pilot_ready": False,
        "metrics_endpoint_enabled": False,
    }


@router.get("/jwks")
def admin_jwks(
    _: Annotated[AdminUser, Depends(require_permissions("cdn.read"))],
) -> dict[str, Any]:
    """Public verification keys only (admin-gated in Phase 3)."""
    _require_control_plane()
    return grant_svc.public_jwks()


@router.get("/nodes", response_model=list[BranchCacheNodeOut])
def list_nodes(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.read"))],
    site_id: str | None = None,
) -> list[dict[str, Any]]:
    _require_control_plane()
    try:
        nodes = reg.list_nodes(db, site_id=site_id)
    except BranchCacheValidationError as exc:
        raise _http_validation(exc) from exc
    return [reg.node_to_public_dict(n) for n in nodes]


@router.post("/nodes", response_model=BranchCacheNodeCreateOut, status_code=status.HTTP_201_CREATED)
def create_node(
    payload: BranchCacheNodeCreateIn,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> dict[str, Any]:
    _require_control_plane()
    try:
        node, enrollment = reg.create_node(
            db,
            admin=admin,
            node_id=payload.node_id,
            display_name=payload.display_name,
            site_id=payload.site_id,
            base_url=payload.base_url,
            branch_code=payload.branch_code,
            capacity_bytes=payload.capacity_bytes,
            software_version=payload.software_version,
            protocol_version=payload.protocol_version,
            issue_enrollment_token=payload.issue_enrollment_token,
        )
    except BranchCacheValidationError as exc:
        raise _http_validation(exc) from exc
    metrics.incr("nodes_created")
    return {"node": reg.node_to_public_dict(node), "enrollment_token": enrollment}


@router.get("/nodes/{node_id}", response_model=BranchCacheNodeOut)
def get_node(
    node_id: str,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.read"))],
) -> dict[str, Any]:
    _require_control_plane()
    node = reg.get_node_by_node_id(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return reg.node_to_public_dict(node)


@router.patch("/nodes/{node_id}", response_model=BranchCacheNodeOut)
def patch_node(
    node_id: str,
    payload: BranchCacheNodeUpdateIn,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> dict[str, Any]:
    _require_control_plane()
    node = reg.get_node_by_node_id(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    data = payload.model_dump(exclude_unset=True)
    try:
        updated = reg.update_node(db, node, **data)
    except BranchCacheValidationError as exc:
        raise _http_validation(exc) from exc
    return reg.node_to_public_dict(updated)


@router.post("/nodes/{node_id}/enrollment-token")
def rotate_enrollment(
    node_id: str,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> dict[str, str]:
    """Rotate one-time enrollment token. Raw returned once; hash stored only."""
    _require_control_plane()
    node = reg.get_node_by_node_id(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    raw = reg.rotate_enrollment_token(db, node)
    return {"enrollment_token": raw, "node_id": node.node_id}


@router.post("/nodes/{node_id}/heartbeat", response_model=BranchCacheNodeOut)
def heartbeat(
    node_id: str,
    payload: BranchCacheHeartbeatIn,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> dict[str, Any]:
    """Admin/lab heartbeat recorder. Production nodes should use mTLS at proxy."""
    _require_control_plane()
    node = reg.get_node_by_node_id(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    try:
        updated = reg.record_heartbeat(
            db,
            node,
            used_bytes=payload.used_bytes,
            capacity_bytes=payload.capacity_bytes,
            software_version=payload.software_version,
            protocol_version=payload.protocol_version,
            healthy=payload.healthy,
            enrollment_token=payload.enrollment_token,
        )
    except BranchCacheValidationError as exc:
        raise _http_validation(exc) from exc
    metrics.incr("heartbeats_recorded")
    return reg.node_to_public_dict(updated)


@router.post("/routing/dry-run")
def routing_dry_run(
    payload: BranchCacheRouteDryRunIn,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.read"))],
) -> dict[str, Any]:
    """Shadow routing decision — does not redirect clients or alter playback."""
    _require_control_plane()
    decision = route_svc.select_branch_cache_node(
        db,
        site_id=payload.site_id,
        package_id=payload.package_id,
        require_bytes=payload.require_bytes,
        shadow=True,
    )
    metrics.incr("routing_decisions")
    if decision.mode == "branch_cache":
        metrics.incr("routing_branch_selected")
    else:
        metrics.incr("routing_central_fallback")
    return decision.as_dict()


@router.post("/edge-grants/issue")
def issue_grant(
    payload: BranchCacheEdgeGrantIssueIn,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> dict[str, Any]:
    """Issue a short-lived edge grant for verification labs. Not used for live redirect."""
    _require_control_plane()
    cfg = get_settings()
    if not cfg.enable_edge_grant_issue:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Feature disabled",
        )
    try:
        token, claims = grant_svc.issue_edge_grant(
            node_id=payload.node_id,
            site_id=payload.site_id,
            package_id=payload.package_id,
            session_id=payload.session_id,
            path_prefix=payload.path_prefix,
            ttl_seconds=payload.ttl_seconds,
        )
    except (grant_svc.EdgeGrantError, BranchCacheValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    metrics.incr("edge_grants_issued")
    return {
        "token": token,
        "claims": claims.as_dict(),
        "alg": grant_svc.EDGE_GRANT_ALG,
        "kid": claims.kid,
    }


@router.post("/edge-grants/verify")
def verify_grant(
    payload: BranchCacheEdgeGrantVerifyIn,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> dict[str, Any]:
    """Verify an edge grant with public key (lab). Does not consume playback sessions."""
    _require_control_plane()
    try:
        claims = grant_svc.verify_edge_grant(
            payload.token,
            expected_node_id=payload.node_id,
            expected_package_id=payload.package_id,
            expected_path=payload.path,
        )
    except (grant_svc.EdgeGrantError, BranchCacheValidationError) as exc:
        metrics.incr("edge_grants_verified_fail")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    metrics.incr("edge_grants_verified_ok")
    return {"valid": True, "claims": claims.as_dict(), "alg": grant_svc.EDGE_GRANT_ALG}
