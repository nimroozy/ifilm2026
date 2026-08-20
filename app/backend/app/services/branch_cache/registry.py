"""Branch cache-node registry helpers (admin control plane)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.runtime import is_prod_like
from app.models.admin import AdminUser
from app.models.branch_cache import (
    HEALTH_HEALTHY,
    HEALTH_UNHEALTHY,
    HEALTH_UNKNOWN,
    STATUS_DISABLED,
    STATUS_OFFLINE,
    STATUS_ONLINE,
    STATUS_PENDING,
    BranchCacheNode,
    utcnow,
)
from app.models.media_assets import new_uuid
from app.services.branch_cache.validation import (
    BranchCacheValidationError,
    validate_base_url,
    validate_node_id,
    validate_site_id,
)

ALLOWED_STATUS = frozenset(
    {STATUS_PENDING, STATUS_ONLINE, "degraded", STATUS_OFFLINE, STATUS_DISABLED, "draining"}
)


def hash_heartbeat_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_enrollment_token() -> str:
    """One-time bootstrap secret (return once; store hash only)."""
    return secrets.token_urlsafe(32)


def node_to_public_dict(node: BranchCacheNode) -> dict[str, Any]:
    """Secret-free node representation for APIs."""
    return {
        "id": node.id,
        "node_id": node.node_id,
        "display_name": node.display_name,
        "site_id": node.site_id,
        "branch_code": node.branch_code,
        "base_url": node.base_url,
        "status": node.status,
        "draining": bool(node.draining),
        "disabled": bool(node.disabled),
        "software_version": node.software_version,
        "protocol_version": node.protocol_version,
        "capacity_bytes": node.capacity_bytes,
        "used_bytes": int(node.used_bytes or 0),
        "free_bytes": (
            max(0, int(node.capacity_bytes) - int(node.used_bytes or 0))
            if node.capacity_bytes is not None
            else None
        ),
        "last_heartbeat_at": node.last_heartbeat_at.isoformat() if node.last_heartbeat_at else None,
        "last_health_ok_at": node.last_health_ok_at.isoformat() if node.last_health_ok_at else None,
        "health_status": node.health_status,
        "has_heartbeat_token": bool(node.heartbeat_token_hash),
        "node_key_id": node.node_key_id,
        "has_node_public_key": bool(node.node_public_key_pem),
        "created_by_admin_id": node.created_by_admin_id,
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
        "disabled_at": node.disabled_at.isoformat() if node.disabled_at else None,
        # Never: heartbeat_token_hash, enrollment secrets, private keys, customer data.
    }


def create_node(
    db: Session,
    *,
    admin: AdminUser,
    node_id: str,
    display_name: str,
    site_id: str,
    base_url: str,
    branch_code: str | None = None,
    capacity_bytes: int | None = None,
    software_version: str | None = None,
    protocol_version: str | None = None,
    settings: Settings | None = None,
    issue_enrollment_token: bool = False,
) -> tuple[BranchCacheNode, str | None]:
    cfg = settings or get_settings()
    nid = validate_node_id(node_id)
    site = validate_site_id(site_id)
    allow_http = not is_prod_like(cfg.app_env)
    url = validate_base_url(base_url, allow_http=allow_http)
    name = (display_name or "").strip()
    if not name or len(name) > 255:
        raise BranchCacheValidationError("display_name is required", code="invalid_display_name")

    existing = db.query(BranchCacheNode).filter(BranchCacheNode.node_id == nid).one_or_none()
    if existing is not None:
        raise BranchCacheValidationError("node_id already registered", code="duplicate_node_id")

    enrollment: str | None = None
    token_hash: str | None = None
    if issue_enrollment_token:
        enrollment = generate_enrollment_token()
        token_hash = hash_heartbeat_token(enrollment)

    node = BranchCacheNode(
        id=new_uuid(),
        node_id=nid,
        display_name=name,
        site_id=site,
        branch_code=(branch_code or "").strip() or None,
        base_url=url,
        status=STATUS_PENDING,
        draining=False,
        disabled=False,
        software_version=(software_version or "").strip() or None,
        protocol_version=(protocol_version or "").strip() or None,
        capacity_bytes=capacity_bytes,
        used_bytes=0,
        health_status=HEALTH_UNKNOWN,
        heartbeat_token_hash=token_hash,
        created_by_admin_id=admin.id,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node, enrollment


def update_node(
    db: Session,
    node: BranchCacheNode,
    *,
    settings: Settings | None = None,
    display_name: str | None = None,
    site_id: str | None = None,
    base_url: str | None = None,
    branch_code: str | None = ...,  # type: ignore[assignment]
    status: str | None = None,
    draining: bool | None = None,
    disabled: bool | None = None,
    capacity_bytes: int | None = ...,  # type: ignore[assignment]
    software_version: str | None = ...,  # type: ignore[assignment]
    protocol_version: str | None = ...,  # type: ignore[assignment]
) -> BranchCacheNode:
    cfg = settings or get_settings()
    if display_name is not None:
        name = display_name.strip()
        if not name or len(name) > 255:
            raise BranchCacheValidationError(
                "display_name is required", code="invalid_display_name"
            )
        node.display_name = name
    if site_id is not None:
        node.site_id = validate_site_id(site_id)
    if base_url is not None:
        allow_http = not is_prod_like(cfg.app_env)
        node.base_url = validate_base_url(base_url, allow_http=allow_http)
    if branch_code is not ...:
        node.branch_code = (branch_code or "").strip() or None
    if status is not None:
        if status not in ALLOWED_STATUS:
            raise BranchCacheValidationError("invalid status", code="invalid_status")
        node.status = status
    if draining is not None:
        node.draining = bool(draining)
        if node.draining and node.status == STATUS_ONLINE:
            node.status = "draining"
    if disabled is not None:
        node.disabled = bool(disabled)
        if node.disabled:
            node.status = STATUS_DISABLED
            node.disabled_at = utcnow()
        elif node.status == STATUS_DISABLED:
            node.status = STATUS_PENDING
            node.disabled_at = None
    if capacity_bytes is not ...:
        node.capacity_bytes = capacity_bytes
    if software_version is not ...:
        node.software_version = (software_version or "").strip() or None
    if protocol_version is not ...:
        node.protocol_version = (protocol_version or "").strip() or None
    node.updated_at = utcnow()
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def rotate_enrollment_token(db: Session, node: BranchCacheNode) -> str:
    """Issue a new one-time enrollment token; store hash only. Returns raw once."""
    raw = generate_enrollment_token()
    node.heartbeat_token_hash = hash_heartbeat_token(raw)
    node.updated_at = utcnow()
    db.add(node)
    db.commit()
    db.refresh(node)
    return raw


def record_heartbeat(
    db: Session,
    node: BranchCacheNode,
    *,
    used_bytes: int | None = None,
    capacity_bytes: int | None = None,
    software_version: str | None = None,
    protocol_version: str | None = None,
    healthy: bool = True,
    enrollment_token: str | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> BranchCacheNode:
    """Record a heartbeat. Optional enrollment_token checked against stored hash.

    Prefer mTLS at the trusted proxy for production nodes; this path supports
    lab/admin simulation and future hashed bootstrap without logging secrets.
    """
    cfg = settings or get_settings()
    clock = now or datetime.now(UTC)

    if enrollment_token is not None:
        if not node.heartbeat_token_hash:
            raise BranchCacheValidationError(
                "node has no enrollment token configured",
                code="no_enrollment",
            )
        digest = hash_heartbeat_token(enrollment_token)
        if not secrets.compare_digest(digest, node.heartbeat_token_hash):
            raise BranchCacheValidationError("invalid enrollment token", code="auth_failed")

    if used_bytes is not None:
        if used_bytes < 0:
            raise BranchCacheValidationError("used_bytes must be >= 0", code="invalid_capacity")
        node.used_bytes = int(used_bytes)
    if capacity_bytes is not None:
        if capacity_bytes < 0:
            raise BranchCacheValidationError("capacity_bytes must be >= 0", code="invalid_capacity")
        node.capacity_bytes = int(capacity_bytes)
    if software_version is not None:
        node.software_version = software_version.strip() or None
    if protocol_version is not None:
        node.protocol_version = protocol_version.strip() or None

    node.last_heartbeat_at = clock
    if healthy:
        node.health_status = HEALTH_HEALTHY
        node.last_health_ok_at = clock
        if node.status in {STATUS_PENDING, STATUS_OFFLINE, "degraded"} and not node.disabled:
            # Hysteresis: pending/offline → online on healthy heartbeat when not draining.
            if not node.draining:
                node.status = STATUS_ONLINE
    else:
        node.health_status = HEALTH_UNHEALTHY
        if node.status == STATUS_ONLINE:
            node.status = "degraded"

    # Stale capacity hysteresis vs min free is evaluated at routing time.
    _ = cfg  # reserved for future drain auto-policy
    node.updated_at = utcnow()
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def get_node_by_node_id(db: Session, node_id: str) -> BranchCacheNode | None:
    try:
        nid = validate_node_id(node_id)
    except BranchCacheValidationError:
        return None
    return db.query(BranchCacheNode).filter(BranchCacheNode.node_id == nid).one_or_none()


def list_nodes(db: Session, *, site_id: str | None = None) -> list[BranchCacheNode]:
    q = db.query(BranchCacheNode)
    if site_id:
        q = q.filter(BranchCacheNode.site_id == validate_site_id(site_id))
    return q.order_by(BranchCacheNode.node_id.asc()).all()
