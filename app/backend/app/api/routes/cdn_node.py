"""Node-facing CDN APIs (CDN-P1): authenticated heartbeat + central origin pull.

Authentication: ``Authorization: Bearer <node token>`` + ``X-Ifilm-Node-Id``.
The token is compared against a SHA-256 hash; nothing here returns storage
credentials, and browsers never call these routes.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from app.core.config import get_settings
from app.core.deps import DbSession
from app.core.features import require_feature
from app.models.cdn_management import ManagedCDNNode
from app.schemas.cdn_management import NodeHeartbeatIn
from app.services import cdn_management as svc
from app.services.cdn_origin import CDNOriginError, read_package_object

logger = logging.getLogger("app.cdn.node_api")

router = APIRouter(prefix="/cdn", tags=["cdn-node"])


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid node credential",
        headers={"WWW-Authenticate": "Bearer"},
    )


def authenticate_node(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    x_ifilm_node_id: Annotated[str | None, Header(alias="X-Ifilm-Node-Id")] = None,
) -> ManagedCDNNode:
    require_feature("enable_cdn_node_api")
    node_id = (x_ifilm_node_id or "").strip()
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not node_id or not token or len(node_id) > 36 or len(token) > 512:
        raise _unauthorized()
    node = db.get(ManagedCDNNode, node_id)
    if node is None or not svc.verify_heartbeat_token(node, token):
        raise _unauthorized()
    if not node.enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Node is disabled")
    return node


AuthenticatedNode = Annotated[ManagedCDNNode, Depends(authenticate_node)]


@router.post("/nodes/{node_id}/heartbeat")
def node_heartbeat(
    node_id: str, payload: NodeHeartbeatIn, db: DbSession, node: AuthenticatedNode
) -> dict[str, Any]:
    if node.id != node_id:
        raise _unauthorized()
    result = svc.record_heartbeat(db, node, payload.model_dump(exclude_unset=True))
    # Never return the full public dict to nodes (keeps response minimal).
    result.pop("node", None)
    return result


@router.api_route("/origin/{asset_id}/{package_id}/{relative_path:path}", methods=["GET", "HEAD"])
def origin_object(
    asset_id: str,
    package_id: str,
    relative_path: str,
    request: Request,
    db: DbSession,
    node: AuthenticatedNode,
) -> Response:
    settings = get_settings()
    try:
        obj = read_package_object(
            db,
            asset_id=asset_id,
            package_id=package_id,
            relative_path=relative_path,
            settings=settings,
        )
    except CDNOriginError as exc:
        ref = hashlib.sha256(f"{asset_id}/{package_id}/{relative_path}".encode()).hexdigest()[:16]
        logger.info(
            "event=origin_denied node_id=%s object_ref=%s code=%s", node.id, ref, exc.code
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Ifilm-Sha256": obj.sha256,
        "X-Ifilm-Origin": obj.source,
        "Content-Length": str(len(obj.data)),
    }
    body = b"" if request.method.upper() == "HEAD" else obj.data
    return Response(content=body, media_type=obj.content_type, headers=headers)
