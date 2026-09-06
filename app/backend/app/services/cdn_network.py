"""Admin-managed CDN network policy: management (SSH) and serve (media) CIDRs.

Fail-closed rules enforced here and by the provisioner:
- Management CIDRs are REQUIRED before any firewall is applied; empty never
  means "allow any".
- Serve CIDRs default to empty, which renders NO media-port ingress rule
  (CDN-P1: edge playback is disabled, so the media port stays closed).
- ``0.0.0.0/0`` / ``::/0`` are accepted only when entered explicitly AND
  confirmed; they are never introduced implicitly.
Values live in ``app_settings`` (non-secret) with env fallbacks.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.admin import AdminUser
from app.models.app_settings import AppSetting

logger = logging.getLogger(__name__)

MANAGEMENT_KEY = "cdn.management_cidrs"
SERVE_KEY = "cdn.serve_cidrs"
ALLOW_ANY = frozenset({"0.0.0.0/0", "::/0"})
MAX_CIDRS = 64


class CDNNetworkError(ValueError):
    pass


def parse_cidr_list(raw: str | Iterable[str] | None, *, field: str) -> list[str]:
    """Validate and canonicalise a comma/newline-separated CIDR list (strict)."""
    items: list[str]
    if raw is None:
        items = []
    elif isinstance(raw, str):
        items = [part for chunk in raw.replace("\n", ",").split(",") for part in [chunk.strip()] if part]
    else:
        items = [str(part).strip() for part in raw if str(part).strip()]
    result: list[str] = []
    for item in items:
        try:
            network = ipaddress.ip_network(item, strict=True)
        except ValueError as exc:
            raise CDNNetworkError(
                f"{field}: '{item}' is not a valid CIDR network (use e.g. 103.126.4.0/24)"
            ) from exc
        text = str(network)
        if text not in result:
            result.append(text)
    if len(result) > MAX_CIDRS:
        raise CDNNetworkError(f"{field}: at most {MAX_CIDRS} networks are allowed")
    return result


def contains_allow_any(cidrs: Iterable[str]) -> bool:
    return any(c in ALLOW_ANY for c in cidrs)


def _row_value(db: Session, key: str) -> tuple[str | None, datetime | None]:
    row = db.get(AppSetting, key)
    if row is None:
        return None, None
    return row.value, row.updated_at


def get_network_settings(db: Session, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    mgmt_raw, mgmt_at = _row_value(db, MANAGEMENT_KEY)
    serve_raw, serve_at = _row_value(db, SERVE_KEY)
    source = "db" if mgmt_raw is not None or serve_raw is not None else "env"
    mgmt_text = mgmt_raw if mgmt_raw is not None else (cfg.cdn_management_cidrs or "")
    serve_text = serve_raw if serve_raw is not None else (cfg.cdn_serve_cidrs or "")
    try:
        management = parse_cidr_list(mgmt_text, field="management_cidrs")
    except CDNNetworkError:
        management = []
    try:
        serve = parse_cidr_list(serve_text, field="serve_cidrs")
    except CDNNetworkError:
        serve = []
    updated = max((t for t in (mgmt_at, serve_at) if t is not None), default=None)
    return {
        "management_cidrs": management,
        "serve_cidrs": serve,
        "source": source if (management or serve) else "unset",
        "management_configured": bool(management),
        "management_allow_any": contains_allow_any(management),
        "serve_allow_any": contains_allow_any(serve),
        "media_port_open": bool(serve),
        "provisioning_ready": bool(management),
        "updated_at": updated.isoformat() if updated else None,
    }


def effective_network(db: Session, settings: Settings | None = None) -> tuple[list[str], list[str]]:
    data = get_network_settings(db, settings)
    return list(data["management_cidrs"]), list(data["serve_cidrs"])


def update_network_settings(
    db: Session,
    admin: AdminUser,
    *,
    management_cidrs: str | Iterable[str] | None,
    serve_cidrs: str | Iterable[str] | None,
    confirm_allow_any: bool = False,
) -> dict[str, Any]:
    management = parse_cidr_list(management_cidrs, field="management_cidrs")
    serve = parse_cidr_list(serve_cidrs, field="serve_cidrs")
    if not management:
        raise CDNNetworkError("At least one management CIDR is required before provisioning")
    if (contains_allow_any(management) or contains_allow_any(serve)) and not confirm_allow_any:
        raise CDNNetworkError(
            "0.0.0.0/0 or ::/0 exposes the port to the whole Internet; confirm explicitly to allow it"
        )
    now = datetime.now(UTC)
    for key, value in ((MANAGEMENT_KEY, ",".join(management)), (SERVE_KEY, ",".join(serve))):
        row = db.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key, value=value, updated_at=now)
        else:
            row.value = value
            row.updated_at = now
        db.add(row)
    db.commit()
    logger.info(
        "cdn_network_event event=updated admin_id=%s management=%d serve=%d allow_any=%s",
        admin.id,
        len(management),
        len(serve),
        contains_allow_any(management) or contains_allow_any(serve),
    )
    return get_network_settings(db)


def address_in_networks(address: str, cidrs: Iterable[str]) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    for cidr in cidrs:
        network = ipaddress.ip_network(cidr, strict=False)
        if ip.version == network.version and ip in network:
            return True
    return False
