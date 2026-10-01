"""CDN-P1 routing engine over ``managed_cdn_nodes`` + ``cdn_prefix_routes``.

Decision order (documented in the admin UI):

1. Longest matching CIDR prefix wins.
2. Equal prefix length: the lower ``priority`` number wins, then node name.
3. Ineligible preferred node → next eligible matching rule.
4. → eligible cache node in the same branch/location as the preferred node.
5. → default Main CDN → secondary Main CDN nodes by priority.
6. → central iFilm playback (``/api/stream``), which is always the final answer.

Eligibility: enabled, not draining, provisioned, heartbeat fresh, no failed
provisioning state. CDN-P1 uses this engine for admin lookups only; customer
playback is not redirected until CDN-P2 enables ``ENABLE_CDN_EDGE_ROUTING``.
"""

from __future__ import annotations

import ipaddress
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.cdn_management import CDNPrefixRoute, ManagedCDNNode
from app.services import cdn_management as mgmt

REASON_DISABLED = "disabled"
REASON_DRAINING = "draining"
REASON_NOT_PROVISIONED = "not_provisioned"
REASON_PROVISION_FAILED = "provision_failed"
REASON_NO_HEARTBEAT = "no_heartbeat"
REASON_STALE_HEARTBEAT = "stale_heartbeat"
REASON_UNHEALTHY = "unhealthy"

STAGE_PREFERRED = "preferred_rule"
STAGE_NEXT_RULE = "next_matching_rule"
STAGE_SAME_BRANCH = "same_branch_cache"
STAGE_DEFAULT_MAIN = "default_main"
STAGE_SECONDARY_MAIN = "secondary_main"
STAGE_CENTRAL = "central"


def node_ineligibility_reason(
    node: ManagedCDNNode, *, now: datetime, stale_seconds: int
) -> str | None:
    """Return why a node cannot receive traffic, or None when eligible."""
    if not node.enabled:
        return REASON_DISABLED
    if node.draining:
        return REASON_DRAINING
    if node.provision_status == mgmt.PROVISION_FAILED:
        return REASON_PROVISION_FAILED
    if node.provision_status != mgmt.PROVISION_READY:
        return REASON_NOT_PROVISIONED
    if node.last_heartbeat_at is None:
        return REASON_NO_HEARTBEAT
    if not mgmt.heartbeat_fresh(node, now=now, stale_seconds=stale_seconds):
        return REASON_STALE_HEARTBEAT
    if node.health_status in {"failed", "unhealthy"}:
        return REASON_UNHEALTHY
    return None


def _candidate(
    node: ManagedCDNNode,
    *,
    stage: str,
    now: datetime,
    stale_seconds: int,
    settings: Settings,
    route: CDNPrefixRoute | None = None,
) -> dict[str, Any]:
    reason = node_ineligibility_reason(node, now=now, stale_seconds=stale_seconds)
    return {
        "stage": stage,
        "node_id": node.id,
        "node_name": node.name,
        "role": node.role,
        "role_label": mgmt.ROLE_LABELS.get(node.role, node.role),
        "branch": node.branch,
        "matched_cidr": route.cidr if route else None,
        "rule_priority": route.priority if route else None,
        "node_priority": int(node.priority or 100),
        "eligible": reason is None,
        "reason": reason or "eligible",
        "state": mgmt.node_state(node, now=now, stale_seconds=stale_seconds),
        "serve_base_url": node.serve_base_url,
    }


def evaluate_route(
    db: Session,
    client_ip: str,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the full decision chain for a client IP (admin routing tester)."""
    cfg = settings or get_settings()
    clock = now or mgmt.utcnow()
    stale = int(cfg.cdn_node_heartbeat_stale_seconds)
    try:
        address = ipaddress.ip_address((client_ip or "").strip())
    except ValueError as exc:
        raise mgmt.CDNManagementError("Invalid client IP address") from exc

    chain: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    reason = "no_matching_rule"
    matched_cidr: str | None = None
    preferred_branch: str | None = None
    considered: set[str] = set()

    def consider(node: ManagedCDNNode, stage: str, route: CDNPrefixRoute | None = None) -> bool:
        nonlocal selected, reason
        entry = _candidate(
            node, stage=stage, now=clock, stale_seconds=stale, settings=cfg, route=route
        )
        chain.append(entry)
        considered.add(node.id)
        if entry["eligible"] and selected is None:
            selected = mgmt.node_public(node, cfg)
            reason = stage
            return True
        return False

    # 1–3: matching rules, longest prefix → lowest priority number → node name.
    matches: list[tuple[int, int, str, CDNPrefixRoute, ManagedCDNNode]] = []
    for route, node in (
        db.query(CDNPrefixRoute, ManagedCDNNode)
        .join(ManagedCDNNode)
        .filter(CDNPrefixRoute.enabled.is_(True))
        .all()
    ):
        network = ipaddress.ip_network(route.cidr)
        if address.version == network.version and address in network:
            matches.append((network.prefixlen, int(route.priority), node.name, route, node))
    matches.sort(key=lambda item: (-item[0], item[1], item[2]))
    for index, (_, _, _, route, node) in enumerate(matches):
        if index == 0:
            matched_cidr = route.cidr
            preferred_branch = (node.branch or "").strip().lower() or None
        stage = STAGE_PREFERRED if index == 0 else STAGE_NEXT_RULE
        if consider(node, stage, route):
            break

    # 4: eligible cache in the same branch as the preferred node.
    if selected is None and preferred_branch:
        for node in (
            db.query(ManagedCDNNode)
            .filter(ManagedCDNNode.role == "cache", ManagedCDNNode.id.notin_(considered))
            .order_by(ManagedCDNNode.priority.asc(), ManagedCDNNode.name)
            .all()
        ):
            if (node.branch or "").strip().lower() != preferred_branch:
                continue
            if consider(node, STAGE_SAME_BRANCH):
                break

    # 5: default main, then secondary mains by priority.
    if selected is None:
        mains = (
            db.query(ManagedCDNNode)
            .filter(ManagedCDNNode.role == "main")
            .order_by(
                ManagedCDNNode.is_default.desc(),
                ManagedCDNNode.priority.asc(),
                ManagedCDNNode.name,
            )
            .all()
        )
        for node in mains:
            if node.id in considered:
                continue
            stage = STAGE_DEFAULT_MAIN if node.is_default else STAGE_SECONDARY_MAIN
            if consider(node, stage):
                break

    # 6: central playback is always the last entry and always eligible.
    chain.append(
        {
            "stage": STAGE_CENTRAL,
            "node_id": None,
            "node_name": "iFilm central",
            "role": "central",
            "role_label": "CENTRAL",
            "branch": None,
            "matched_cidr": None,
            "rule_priority": None,
            "node_priority": None,
            "eligible": True,
            "reason": "always_available",
            "state": "central",
            "serve_base_url": None,
        }
    )
    if selected is None:
        reason = "central_fallback" if matches or chain[:-1] else "no_nodes_configured"

    return {
        "client_ip": str(address),
        "matched_cidr": matched_cidr,
        "selected": selected,
        "selected_stage": reason if selected else STAGE_CENTRAL,
        "reason": reason,
        "chain": chain,
        "edge_routing_enabled": bool(cfg.enable_cdn_edge_routing),
        "central_fallback": True,
    }
