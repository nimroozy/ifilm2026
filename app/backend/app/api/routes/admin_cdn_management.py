"""Admin CDN management APIs. Responses are deliberately secret-free.

Permissions: ``cdn.read`` for reads, ``cdn.manage`` for inventory mutations,
``cdn.provision`` for SSH/provisioning actions, ``cdn.routing`` for prefix
rules, ``cdn.secrets`` for storage/R2 credentials.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from app.core.config import get_settings
from app.core.deps import DbSession, require_permissions
from app.models.admin import AdminUser
from app.models.cdn_management import CDNPrefixRoute
from app.schemas.cdn_management import (
    ConfirmedActionIn,
    ManagedNodeIn,
    ManagedNodePatch,
    NetworkSettingsIn,
    NodeHeartbeatIn,
    PinHostKeyIn,
    PrefixRouteIn,
    PrefixRoutePatch,
    R2SettingsIn,
    RouteLookupIn,
)
from app.services import cdn_management as svc
from app.services import cdn_network
from app.services.cdn_provisioner import probe_ssh_connection
from app.services.cdn_routing import evaluate_route

router = APIRouter(prefix="/admin/cdn-management", tags=["admin-cdn-management"])

CdnRead = Annotated[AdminUser, Depends(require_permissions("cdn.read"))]
CdnManage = Annotated[AdminUser, Depends(require_permissions("cdn.manage"))]
CdnProvision = Annotated[AdminUser, Depends(require_permissions("cdn.provision"))]
CdnRouting = Annotated[AdminUser, Depends(require_permissions("cdn.routing"))]
CdnSecrets = Annotated[AdminUser, Depends(require_permissions("cdn.secrets"))]


def bad(exc: svc.CDNManagementError, code: int = 400) -> HTTPException:
    return HTTPException(status_code=code, detail=str(exc))


def _require_confirm(payload: ConfirmedActionIn | None) -> None:
    if payload is None or not payload.confirm:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required")


def _load_node(db: DbSession, node_id: str):
    try:
        return svc.get_node(db, node_id)
    except svc.CDNManagementError as exc:
        raise bad(exc, 404) from exc


# --- Storage / R2 -----------------------------------------------------------


@router.get("/r2")
def get_r2(db: DbSession, _: CdnSecrets) -> dict[str, Any]:
    return svc.get_r2(db)


@router.put("/r2")
def put_r2(payload: R2SettingsIn, db: DbSession, admin: CdnSecrets) -> dict[str, Any]:
    try:
        return svc.update_r2(db, admin, payload.model_dump())
    except svc.CDNManagementError as exc:
        raise bad(exc) from exc


@router.post("/r2/test")
def test_r2(db: DbSession, admin: CdnSecrets) -> dict[str, Any]:
    try:
        return svc.test_r2_connection(db, admin)
    except svc.CDNManagementError as exc:
        raise bad(exc) from exc


# --- Overview / status ------------------------------------------------------


@router.get("/status")
def status_flags(_: CdnRead) -> dict[str, Any]:
    return svc.status_flags()


@router.get("/overview")
def overview(db: DbSession, _: CdnRead) -> dict[str, Any]:
    return svc.overview(db)


# --- Network policy (management SSH + media serve CIDRs) --------------------


@router.get("/network")
def get_network(db: DbSession, _: CdnRead) -> dict[str, Any]:
    return cdn_network.get_network_settings(db)


@router.put("/network")
def put_network(payload: NetworkSettingsIn, db: DbSession, admin: CdnProvision) -> dict[str, Any]:
    try:
        return cdn_network.update_network_settings(
            db,
            admin,
            management_cidrs=payload.management_cidrs,
            serve_cidrs=payload.serve_cidrs,
            confirm_allow_any=payload.confirm_allow_any,
        )
    except cdn_network.CDNNetworkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- Nodes ------------------------------------------------------------------


@router.get("/nodes")
def nodes(db: DbSession, _: CdnRead) -> list[dict[str, Any]]:
    return svc.list_nodes(db)


@router.post("/nodes", status_code=201)
def create_node(payload: ManagedNodeIn, db: DbSession, admin: CdnManage) -> dict[str, Any]:
    try:
        node, token = svc.save_node(db, admin, payload.model_dump())
        return {"node": node, "heartbeat_token": token}
    except svc.CDNManagementError as exc:
        raise bad(exc) from exc


@router.get("/nodes/{node_id}")
def get_node(node_id: str, db: DbSession, _: CdnRead) -> dict[str, Any]:
    return svc.node_public(_load_node(db, node_id))


@router.patch("/nodes/{node_id}")
def update_node(
    node_id: str, payload: ManagedNodePatch, db: DbSession, admin: CdnManage
) -> dict[str, Any]:
    node = _load_node(db, node_id)
    try:
        updated, _ = svc.save_node(db, admin, payload.model_dump(exclude_unset=True), node)
        return updated
    except svc.CDNManagementError as exc:
        raise bad(exc) from exc


@router.delete("/nodes/{node_id}", status_code=204)
def delete_node(node_id: str, confirm: bool, db: DbSession, admin: CdnManage) -> Response:
    if not confirm:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required")
    node = _load_node(db, node_id)
    try:
        svc.delete_node(db, admin, node)
    except svc.CDNManagementError as exc:
        raise bad(exc, 409) from exc
    return Response(status_code=204)


@router.post("/nodes/{node_id}/test-ssh")
def test_ssh(node_id: str, db: DbSession, _: CdnProvision) -> dict[str, Any]:
    """Authenticated SSH probe: host key, OS release, privilege, disk. Bounded."""
    node = _load_node(db, node_id)
    result = probe_ssh_connection(node, settings=get_settings())
    return svc.record_ssh_test(db, node, result)


@router.post("/nodes/{node_id}/pin-host-key")
def pin_host_key(
    node_id: str, payload: PinHostKeyIn, db: DbSession, admin: CdnProvision
) -> dict[str, Any]:
    _require_confirm(ConfirmedActionIn(confirm=payload.confirm))
    node = _load_node(db, node_id)
    try:
        node.ssh_host_key_fingerprint = svc.validate_host_fingerprint(payload.fingerprint)
    except svc.CDNManagementError as exc:
        raise bad(exc, 400) from exc
    db.add(node)
    db.commit()
    db.refresh(node)
    return svc.node_public(node)


@router.post("/nodes/{node_id}/actions/{action}", status_code=202)
def node_action(
    node_id: str,
    action: str,
    payload: ConfirmedActionIn,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("cdn.read"))],
) -> dict[str, Any]:
    if action not in svc.ALL_ACTIONS:
        raise HTTPException(status_code=404, detail="Unknown action")
    _require_confirm(payload)
    # Permission split: state actions need cdn.manage; SSH-backed actions need cdn.provision.
    needed = "cdn.manage" if action in svc.STATE_ACTIONS else "cdn.provision"
    require_permissions(needed)(admin)
    node = _load_node(db, node_id)
    try:
        if action in svc.STATE_ACTIONS:
            return {"node": svc.apply_state_action(db, admin, node, action)}
        return svc.queue_action(db, admin, node, action)
    except svc.CDNManagementError as exc:
        raise bad(exc, 409) from exc


@router.post("/nodes/{node_id}/heartbeat-token")
def rotate_heartbeat_token(
    node_id: str, payload: ConfirmedActionIn, db: DbSession, _: CdnProvision
) -> dict[str, str]:
    _require_confirm(payload)
    node = _load_node(db, node_id)
    token = svc.issue_heartbeat_token(node)
    db.add(node)
    db.commit()
    return {"heartbeat_token": token}


@router.get("/nodes/{node_id}/provision-runs")
def provision_runs(node_id: str, db: DbSession, _: CdnRead) -> list[dict[str, Any]]:
    return svc.list_runs(db, node_id)


@router.post("/nodes/{node_id}/heartbeat")
def heartbeat(
    node_id: str,
    payload: NodeHeartbeatIn,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Legacy token-authenticated heartbeat path (kept for nodes provisioned by PR #91)."""
    node = _load_node(db, node_id)
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not svc.verify_heartbeat_token(node, token):
        raise HTTPException(status_code=401, detail="Invalid node heartbeat credential")
    result = svc.record_heartbeat(db, node, payload.model_dump(exclude_unset=True))
    node_view = result["node"]
    node_view["server_time"] = datetime.now(UTC).isoformat()
    return node_view


# --- Routing ----------------------------------------------------------------


@router.get("/routes")
def routes(db: DbSession, _: CdnRead) -> list[dict[str, Any]]:
    return svc.list_routes(db)


@router.post("/routes", status_code=201)
def create_route(payload: PrefixRouteIn, db: DbSession, _: CdnRouting) -> dict[str, Any]:
    try:
        return svc.save_route(db, payload.model_dump())
    except svc.CDNManagementError as exc:
        raise bad(exc) from exc


@router.patch("/routes/{route_id}")
def update_route(
    route_id: str, payload: PrefixRoutePatch, db: DbSession, _: CdnRouting
) -> dict[str, Any]:
    route = db.get(CDNPrefixRoute, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")
    merged = {
        "cidr": route.cidr,
        "node_id": route.node_id,
        "priority": route.priority,
        "enabled": route.enabled,
        "notes": route.notes,
        **payload.model_dump(exclude_unset=True),
    }
    try:
        return svc.save_route(db, merged, route)
    except svc.CDNManagementError as exc:
        raise bad(exc) from exc


@router.delete("/routes/{route_id}", status_code=204)
def delete_route(route_id: str, confirm: bool, db: DbSession, _: CdnRouting) -> Response:
    if not confirm:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required")
    route = db.get(CDNPrefixRoute, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")
    db.delete(route)
    db.commit()
    return Response(status_code=204)


@router.post("/routes/lookup")
def lookup(payload: RouteLookupIn, db: DbSession, _: CdnRead) -> dict[str, Any]:
    """Routing tester: client IP → matched CIDR → selected node → full fallback chain."""
    try:
        return evaluate_route(db, payload.client_ip)
    except svc.CDNManagementError as exc:
        raise bad(exc) from exc
