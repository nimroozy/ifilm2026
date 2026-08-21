"""Admin CDN management APIs. Responses are deliberately secret-free."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response

from app.core.deps import DbSession, require_permissions
from app.models.admin import AdminUser
from app.models.cdn_management import CDNPrefixRoute, CDNProvisionRun
from app.schemas.cdn_management import (
    ConfirmedActionIn,
    ManagedNodeIn,
    ManagedNodePatch,
    PrefixRouteIn,
    R2SettingsIn,
    RouteLookupIn,
)
from app.services import cdn_management as svc

router = APIRouter(prefix="/admin/cdn-management", tags=["admin-cdn-management"])


def bad(exc: svc.CDNManagementError, code: int = 400) -> HTTPException:
    return HTTPException(status_code=code, detail=str(exc))


@router.get("/r2")
def get_r2(
    db: DbSession, _: Annotated[AdminUser, Depends(require_permissions("settings"))]
) -> dict[str, Any]:
    return svc.get_r2(db)


@router.put("/r2")
def put_r2(
    payload: R2SettingsIn,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("settings"))],
) -> dict[str, Any]:
    try:
        return svc.update_r2(db, admin, payload.model_dump())
    except svc.CDNManagementError as exc:
        raise bad(exc) from exc


@router.get("/nodes")
def nodes(
    db: DbSession, _: Annotated[AdminUser, Depends(require_permissions("cdn.read"))]
) -> list[dict[str, Any]]:
    return svc.list_nodes(db)


@router.post("/nodes", status_code=201)
def create_node(
    payload: ManagedNodeIn,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> dict[str, Any]:
    try:
        return svc.save_node(db, admin, payload.model_dump())
    except svc.CDNManagementError as exc:
        raise bad(exc) from exc


@router.patch("/nodes/{node_id}")
def update_node(
    node_id: str,
    payload: ManagedNodePatch,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> dict[str, Any]:
    try:
        return svc.save_node(
            db, admin, payload.model_dump(exclude_unset=True), svc.get_node(db, node_id)
        )
    except svc.CDNManagementError as exc:
        raise bad(exc, 404 if "not found" in str(exc) else 400) from exc


@router.delete("/nodes/{node_id}", status_code=204)
def delete_node(
    node_id: str,
    confirm: bool,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> Response:
    if not confirm:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required")
    try:
        node = svc.get_node(db, node_id)
    except svc.CDNManagementError as exc:
        raise bad(exc, 404) from exc
    db.delete(node)
    db.commit()
    return Response(status_code=204)


@router.post("/nodes/{node_id}/test-ssh")
def test_ssh(
    node_id: str, db: DbSession, _: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))]
) -> dict[str, Any]:
    try:
        node = svc.get_node(db, node_id)
        result = svc.test_tcp(node)
        if result.get("rtt_ms") is not None:
            node.rtt_ms = result["rtt_ms"]
            db.add(node)
            db.commit()
        return result
    except svc.CDNManagementError as exc:
        raise bad(exc, 404) from exc


@router.post("/nodes/{node_id}/actions/{action}", status_code=202)
def node_action(
    node_id: str,
    action: str,
    payload: ConfirmedActionIn,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> dict[str, Any]:
    allowed = {"provision", "reprovision", "upgrade", "drain", "disable", "clear-cache"}
    if action not in allowed:
        raise HTTPException(status_code=404, detail="Unknown action")
    if not payload.confirm:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required")
    try:
        node = svc.get_node(db, node_id)
    except svc.CDNManagementError as exc:
        raise bad(exc, 404) from exc
    if action == "drain":
        node.draining = True
    if action == "disable":
        node.enabled = False
    db.add(node)
    return svc.queue_action(db, admin, node, action)


@router.get("/nodes/{node_id}/provision-runs")
def provision_runs(
    node_id: str, db: DbSession, _: Annotated[AdminUser, Depends(require_permissions("cdn.read"))]
) -> list[dict[str, Any]]:
    rows = (
        db.query(CDNProvisionRun)
        .filter_by(node_id=node_id)
        .order_by(CDNProvisionRun.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": r.id,
            "action": r.action,
            "status": r.status,
            "log": r.log_text,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in rows
    ]


@router.post("/nodes/{node_id}/heartbeat")
def heartbeat(
    node_id: str,
    payload: dict[str, Any],
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> dict[str, Any]:
    try:
        node = svc.get_node(db, node_id)
    except svc.CDNManagementError as exc:
        raise bad(exc, 404) from exc
    for key in (
        "disk_total_bytes",
        "disk_free_bytes",
        "cached_objects",
        "cached_titles",
        "cache_hits",
        "cache_misses",
        "bandwidth_bytes",
        "rtt_ms",
        "software_version",
        "last_sync_at",
    ):
        if key in payload:
            setattr(node, key, payload[key])
    node.health_status = "online"
    node.last_heartbeat_at = datetime.now(UTC)
    db.add(node)
    db.commit()
    db.refresh(node)
    return svc._node_public(node)


@router.get("/routes")
def routes(
    db: DbSession, _: Annotated[AdminUser, Depends(require_permissions("cdn.read"))]
) -> list[dict[str, Any]]:
    return svc.list_routes(db)


@router.post("/routes", status_code=201)
def create_route(
    payload: PrefixRouteIn,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> dict[str, Any]:
    try:
        return svc.save_route(db, payload.model_dump())
    except svc.CDNManagementError as exc:
        raise bad(exc) from exc


@router.patch("/routes/{route_id}")
def update_route(
    route_id: str,
    payload: PrefixRouteIn,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> dict[str, Any]:
    route = db.get(CDNPrefixRoute, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")
    try:
        return svc.save_route(db, payload.model_dump(), route)
    except svc.CDNManagementError as exc:
        raise bad(exc) from exc


@router.delete("/routes/{route_id}", status_code=204)
def delete_route(
    route_id: str,
    confirm: bool,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.manage"))],
) -> Response:
    if not confirm:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required")
    route = db.get(CDNPrefixRoute, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")
    db.delete(route)
    db.commit()
    return Response(status_code=204)


@router.post("/routes/lookup")
def lookup(
    payload: RouteLookupIn,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("cdn.read"))],
) -> dict[str, Any]:
    try:
        return svc.select_node(db, payload.client_ip)
    except svc.CDNManagementError as exc:
        raise bad(exc) from exc
