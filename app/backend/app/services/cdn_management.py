"""Secret-safe CDN management and deterministic prefix routing."""

from __future__ import annotations

import ipaddress
import json
import socket
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.admin import AdminUser
from app.models.cdn_management import CDNPrefixRoute, CDNProvisionRun, ManagedCDNNode
from app.models.integration_config import IntegrationConfig
from app.services.integration_secrets import IntegrationSecretsError, decrypt_secret, encrypt_secret

R2_PROVIDER = "cloudflare_r2"


class CDNManagementError(ValueError):
    pass


def _encrypt_json(value: dict[str, str], settings: Settings) -> bytes:
    if not settings.integration_secrets_key:
        raise CDNManagementError(
            "INTEGRATION_SECRETS_KEY must be configured before storing credentials"
        )
    try:
        return encrypt_secret(
            plaintext=json.dumps(value), master_key=settings.integration_secrets_key
        )
    except IntegrationSecretsError as exc:
        raise CDNManagementError("Unable to encrypt credentials") from exc


def get_r2(db: Session) -> dict[str, Any]:
    row = db.query(IntegrationConfig).filter_by(provider=R2_PROVIDER).one_or_none()
    data = dict(row.config_json or {}) if row else {}
    return {
        "enabled": bool(row.enabled) if row else False,
        "endpoint_url": data.get("endpoint_url", ""),
        "account_id": data.get("account_id"),
        "bucket": data.get("bucket", ""),
        "region": data.get("region", "auto"),
        "credentials_configured": bool(row and row.secret_ciphertext),
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


def resolve_r2_runtime(db: Session, settings: Settings | None = None) -> dict[str, Any] | None:
    """Resolve the private runtime configuration; never use this in an API response."""
    cfg = settings or get_settings()
    row = db.query(IntegrationConfig).filter_by(provider=R2_PROVIDER).one_or_none()
    if row is None or not row.enabled or not row.secret_ciphertext:
        return None
    try:
        credentials = json.loads(
            decrypt_secret(
                ciphertext=row.secret_ciphertext,
                master_key=cfg.integration_secrets_key,
            )
        )
    except (IntegrationSecretsError, json.JSONDecodeError) as exc:
        raise CDNManagementError("Unable to decrypt R2 credentials") from exc
    data = dict(row.config_json or {})
    return {**data, **credentials, "enabled": True}


def update_r2(
    db: Session, admin: AdminUser, payload: dict[str, Any], settings: Settings | None = None
) -> dict[str, Any]:
    cfg = settings or get_settings()
    parsed = urlparse(str(payload.get("endpoint_url") or ""))
    if parsed.scheme != "https" or not parsed.hostname:
        raise CDNManagementError("R2 endpoint must be a valid HTTPS URL")
    row = db.query(IntegrationConfig).filter_by(provider=R2_PROVIDER).one_or_none()
    if row is None:
        row = IntegrationConfig(provider=R2_PROVIDER, enabled=False, config_json={})
    data = {
        "endpoint_url": str(payload["endpoint_url"]).strip(),
        "account_id": (payload.get("account_id") or "").strip() or None,
        "bucket": str(payload["bucket"]).strip(),
        "region": str(payload.get("region") or "auto").strip(),
    }
    access = (payload.get("access_key_id") or "").strip()
    secret = (payload.get("secret_access_key") or "").strip()
    if bool(access) != bool(secret):
        raise CDNManagementError("Access key and secret key must be supplied together")
    if payload.get("remove_credentials"):
        row.secret_ciphertext = None
    elif access and secret:
        row.secret_ciphertext = _encrypt_json(
            {"access_key_id": access, "secret_access_key": secret}, cfg
        )
    row.enabled = bool(payload.get("enabled"))
    if row.enabled and not row.secret_ciphertext:
        raise CDNManagementError("R2 cannot be enabled without stored credentials")
    row.config_json = data
    row.updated_by_admin_id = admin.id
    row.updated_at = datetime.now(UTC)
    db.add(row)
    db.commit()
    return get_r2(db)


def _node_public(node: ManagedCDNNode) -> dict[str, Any]:
    hits, misses = int(node.cache_hits or 0), int(node.cache_misses or 0)
    return {
        "id": node.id,
        "name": node.name,
        "role": node.role,
        "host": node.host,
        "ssh_port": node.ssh_port,
        "ssh_username": node.ssh_username,
        "credential_type": node.credential_type,
        "credential_configured": bool(node.credential_ciphertext),
        "branch": node.branch,
        "location": node.location,
        "notes": node.notes,
        "enabled": node.enabled,
        "draining": node.draining,
        "is_default": node.is_default,
        "cache_limit_bytes": node.cache_limit_bytes,
        "disk_total_bytes": node.disk_total_bytes,
        "disk_free_bytes": node.disk_free_bytes,
        "cached_objects": node.cached_objects,
        "cached_titles": node.cached_titles,
        "cache_hits": hits,
        "cache_misses": misses,
        "hit_rate": round(hits * 100 / (hits + misses), 2) if hits + misses else None,
        "bandwidth_bytes": node.bandwidth_bytes,
        "rtt_ms": node.rtt_ms,
        "software_version": node.software_version,
        "health_status": node.health_status,
        "provision_status": node.provision_status,
        "last_sync_at": node.last_sync_at.isoformat() if node.last_sync_at else None,
        "last_heartbeat_at": node.last_heartbeat_at.isoformat() if node.last_heartbeat_at else None,
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
    }


def list_nodes(db: Session) -> list[dict[str, Any]]:
    return [_node_public(n) for n in db.query(ManagedCDNNode).order_by(ManagedCDNNode.name).all()]


def get_node(db: Session, node_id: str) -> ManagedCDNNode:
    node = db.get(ManagedCDNNode, node_id)
    if node is None:
        raise CDNManagementError("CDN node not found")
    return node


def save_node(
    db: Session,
    admin: AdminUser,
    payload: dict[str, Any],
    node: ManagedCDNNode | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    node = node or ManagedCDNNode(created_by_admin_id=admin.id)
    for key in (
        "name",
        "role",
        "host",
        "ssh_port",
        "ssh_username",
        "credential_type",
        "branch",
        "location",
        "notes",
        "enabled",
        "is_default",
        "cache_limit_bytes",
    ):
        if key in payload and payload[key] is not None:
            setattr(node, key, payload[key])
    if payload.get("remove_credential"):
        node.credential_ciphertext = None
    elif payload.get("credential"):
        node.credential_ciphertext = _encrypt_json({"value": str(payload["credential"])}, cfg)
    if not node.credential_ciphertext:
        raise CDNManagementError("SSH credential is required")
    if node.is_default and node.role != "main":
        raise CDNManagementError("Only a Main CDN node can be the default")
    if node.is_default:
        db.query(ManagedCDNNode).filter(ManagedCDNNode.id != node.id).update({"is_default": False})
    db.add(node)
    db.commit()
    db.refresh(node)
    return _node_public(node)


def validate_cidr(cidr: str) -> ipaddress._BaseNetwork:
    try:
        return ipaddress.ip_network(cidr.strip(), strict=True)
    except ValueError as exc:
        raise CDNManagementError("CIDR must be a canonical IPv4 or IPv6 network") from exc


def save_route(
    db: Session, payload: dict[str, Any], route: CDNPrefixRoute | None = None
) -> dict[str, Any]:
    network = validate_cidr(str(payload["cidr"]))
    node = get_node(db, str(payload["node_id"]))
    route = route or CDNPrefixRoute()
    route.cidr, route.prefix_length, route.node_id = str(network), network.prefixlen, node.id
    route.priority, route.enabled = (
        int(payload.get("priority", 100)),
        bool(payload.get("enabled", True)),
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return route_public(route, node)


def route_public(route: CDNPrefixRoute, node: ManagedCDNNode | None = None) -> dict[str, Any]:
    return {
        "id": route.id,
        "cidr": route.cidr,
        "prefix_length": route.prefix_length,
        "node_id": route.node_id,
        "node_name": node.name if node else None,
        "priority": route.priority,
        "enabled": route.enabled,
    }


def list_routes(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(CDNPrefixRoute, ManagedCDNNode)
        .join(ManagedCDNNode)
        .order_by(CDNPrefixRoute.prefix_length.desc(), CDNPrefixRoute.priority.asc())
        .all()
    )
    return [route_public(r, n) for r, n in rows]


def select_node(db: Session, client_ip: str) -> dict[str, Any]:
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError as exc:
        raise CDNManagementError("Invalid client IP address") from exc
    candidates = []
    for route, node in (
        db.query(CDNPrefixRoute, ManagedCDNNode)
        .join(ManagedCDNNode)
        .filter(
            CDNPrefixRoute.enabled.is_(True),
            ManagedCDNNode.enabled.is_(True),
            ManagedCDNNode.draining.is_(False),
        )
        .all()
    ):
        network = ipaddress.ip_network(route.cidr)
        if address.version == network.version and address in network:
            candidates.append((network.prefixlen, route.priority, node.name, route, node))
    if candidates:
        _, _, _, route, node = sorted(candidates, key=lambda x: (-x[0], x[1], x[2]))[0]
        return {
            "mode": node.role,
            "reason": "longest_prefix_match",
            "matched_cidr": route.cidr,
            "node": _node_public(node),
        }
    node = (
        db.query(ManagedCDNNode)
        .filter_by(role="main", is_default=True, enabled=True, draining=False)
        .order_by(ManagedCDNNode.name)
        .first()
    )
    if node is None:
        node = (
            db.query(ManagedCDNNode)
            .filter_by(role="main", enabled=True, draining=False)
            .order_by(ManagedCDNNode.name)
            .first()
        )
    return {
        "mode": "main",
        "reason": "main_fallback",
        "matched_cidr": None,
        "node": _node_public(node) if node else None,
    }


def test_tcp(node: ManagedCDNNode, connector=socket.create_connection) -> dict[str, Any]:
    started = datetime.now(UTC)
    try:
        sock = connector((node.host, node.ssh_port), timeout=5)
        sock.close()
    except OSError:
        return {"ok": False, "detail": "SSH port is unreachable"}
    elapsed = max(0, int((datetime.now(UTC) - started).total_seconds() * 1000))
    return {
        "ok": True,
        "detail": "SSH port is reachable; authentication is checked during provisioning",
        "rtt_ms": elapsed,
    }


def queue_action(
    db: Session, admin: AdminUser, node: ManagedCDNNode, action: str
) -> dict[str, Any]:
    run = CDNProvisionRun(
        node_id=node.id,
        action=action,
        status="queued",
        requested_by_admin_id=admin.id,
        log_text="Queued securely. Credentials and command output secrets are never recorded.",
    )
    node.provision_status = "queued"
    db.add_all([run, node])
    db.commit()
    db.refresh(run)
    return {
        "id": run.id,
        "node_id": run.node_id,
        "action": run.action,
        "status": run.status,
        "log": run.log_text,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
