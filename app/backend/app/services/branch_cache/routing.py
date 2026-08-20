"""Deterministic branch-cache routing decision engine (shadow / dry-run).

Phase 3 never redirects clients. Decisions are for admin dry-run and future
data-plane pilots. Central origin remains the mandatory fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.branch_cache import (
    HEALTH_HEALTHY,
    STATUS_DISABLED,
    STATUS_ONLINE,
    BranchCacheNode,
)

# Stable reason codes (low cardinality for metrics/logs).
REASON_CONTROL_PLANE_OFF = "control_plane_off"
REASON_NO_CANDIDATES = "no_eligible_nodes"
REASON_SITE_MISMATCH = "no_site_match"
REASON_STALE_HEARTBEAT = "stale_heartbeat"
REASON_DRAINING = "draining"
REASON_DISABLED = "disabled"
REASON_UNHEALTHY = "unhealthy"
REASON_CAPACITY = "insufficient_capacity"
REASON_PROTOCOL = "protocol_incompatible"
REASON_STATUS = "status_not_online"
REASON_SELECTED = "branch_node_selected"
REASON_CENTRAL_FALLBACK = "central_origin_fallback"


@dataclass(frozen=True)
class RoutingDecision:
    mode: str  # branch_cache | central_origin
    node_id: str | None
    site_id: str
    package_id: str | None
    reason: str
    candidates_considered: int
    shadow: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "node_id": self.node_id,
            "site_id": self.site_id,
            "package_id": self.package_id,
            "reason": self.reason,
            "candidates_considered": self.candidates_considered,
            "shadow": self.shadow,
            "detail": self.detail,
            # Never include base_url credentials (there are none) or tokens.
        }


def _free_bytes(node: BranchCacheNode) -> int | None:
    if node.capacity_bytes is None:
        return None
    used = int(node.used_bytes or 0)
    return max(0, int(node.capacity_bytes) - used)


def _heartbeat_fresh(node: BranchCacheNode, *, now: datetime, stale_seconds: int) -> bool:
    ts = node.last_heartbeat_at
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    age = (now - ts).total_seconds()
    return age <= float(stale_seconds)


def _protocol_ok(node: BranchCacheNode, *, min_version: str) -> bool:
    raw = (node.protocol_version or "").strip()
    if not raw:
        return False
    # Major-compatible: "1" matches "1" / "1.0" / "1.2.3"
    want = (min_version or "1").strip().split(".", 1)[0]
    got = raw.split(".", 1)[0]
    return got == want


def evaluate_node(
    node: BranchCacheNode,
    *,
    site_id: str,
    require_bytes: int,
    now: datetime,
    settings: Settings,
) -> str | None:
    """Return rejection reason code, or None if eligible."""
    if node.disabled or node.status == STATUS_DISABLED:
        return REASON_DISABLED
    if node.draining or node.status == "draining":
        return REASON_DRAINING
    if node.status != STATUS_ONLINE:
        return REASON_STATUS
    if (node.site_id or "").strip().lower() != site_id.strip().lower():
        return REASON_SITE_MISMATCH
    if node.health_status != HEALTH_HEALTHY:
        return REASON_UNHEALTHY
    if not _heartbeat_fresh(
        node, now=now, stale_seconds=int(settings.branch_cache_heartbeat_stale_seconds)
    ):
        return REASON_STALE_HEARTBEAT
    if not _protocol_ok(node, min_version=settings.branch_cache_min_protocol_version):
        return REASON_PROTOCOL
    free = _free_bytes(node)
    min_free = max(int(require_bytes), int(settings.branch_cache_min_free_bytes))
    if free is None or free < min_free:
        return REASON_CAPACITY
    return None


def select_branch_cache_node(
    db: Session,
    *,
    site_id: str,
    package_id: str | None = None,
    require_bytes: int = 0,
    settings: Settings | None = None,
    now: datetime | None = None,
    shadow: bool | None = None,
) -> RoutingDecision:
    """Deterministic selection among eligible nodes; else central-origin fallback.

    Ordering: higher free capacity first, then node_id ascending (stable).
    Cloudflare is never selected here (later optional fallback).
    """
    cfg = settings or get_settings()
    clock = now or datetime.now(UTC)
    site = (site_id or "").strip().lower()
    is_shadow = bool(cfg.enable_branch_cache_shadow_routing if shadow is None else shadow)

    if not cfg.enable_branch_cache_control_plane:
        return RoutingDecision(
            mode="central_origin",
            node_id=None,
            site_id=site,
            package_id=package_id,
            reason=REASON_CONTROL_PLANE_OFF,
            candidates_considered=0,
            shadow=is_shadow,
            detail="branch cache control plane disabled; use central origin",
        )

    if not site:
        return RoutingDecision(
            mode="central_origin",
            node_id=None,
            site_id=site,
            package_id=package_id,
            reason=REASON_NO_CANDIDATES,
            candidates_considered=0,
            shadow=is_shadow,
            detail="site_id required",
        )

    nodes = (
        db.query(BranchCacheNode)
        .filter(BranchCacheNode.site_id == site)
        .order_by(BranchCacheNode.node_id.asc())
        .all()
    )
    eligible: list[tuple[int, str, BranchCacheNode]] = []
    for node in nodes:
        reason = evaluate_node(
            node,
            site_id=site,
            require_bytes=int(require_bytes or 0),
            now=clock,
            settings=cfg,
        )
        if reason is None:
            free = _free_bytes(node) or 0
            eligible.append((free, node.node_id, node))

    if not eligible:
        return RoutingDecision(
            mode="central_origin",
            node_id=None,
            site_id=site,
            package_id=package_id,
            reason=REASON_CENTRAL_FALLBACK if nodes else REASON_NO_CANDIDATES,
            candidates_considered=len(nodes),
            shadow=is_shadow,
            detail="no eligible branch cache node; falling back to central origin",
        )

    # Deterministic: free capacity DESC, node_id ASC
    eligible.sort(key=lambda t: (-t[0], t[1]))
    chosen = eligible[0][2]
    return RoutingDecision(
        mode="branch_cache",
        node_id=chosen.node_id,
        site_id=site,
        package_id=package_id,
        reason=REASON_SELECTED,
        candidates_considered=len(nodes),
        shadow=is_shadow,
        detail="selected eligible healthy node",
    )
