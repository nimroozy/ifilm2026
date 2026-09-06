"""Secret-safe CDN management: storage/R2 settings, managed node inventory, routes.

Design rules (CDN-P1):
- Secrets (R2 keys, SSH bootstrap credentials, generated management keys) are
  Fernet-encrypted with ``INTEGRATION_SECRETS_KEY`` and never returned by APIs.
- Node identity tokens are stored only as SHA-256 hashes.
- Nothing in this module logs credential material.
- Customer playback is untouched: routing here is admin/diagnostic only until
  CDN-P2 enables ``ENABLE_CDN_EDGE_ROUTING``.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.admin import AdminUser
from app.models.cdn_management import CDNPrefixRoute, CDNProvisionRun, ManagedCDNNode
from app.models.integration_config import IntegrationConfig
from app.services.integration_secrets import IntegrationSecretsError, decrypt_secret, encrypt_secret
from app.services.object_storage.s3_compatible import S3CompatibleConfig, probe_s3_connection
from app.services.object_storage.tiers import StorageProviderKind, StorageRole

logger = logging.getLogger(__name__)

R2_PROVIDER = "cloudflare_r2"
STORAGE_PROVIDERS = ("cloudflare_r2", "s3_compatible")
HOST_KEY_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{20,}={0,2}$")
HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))*$"
)
KEY_PREFIX_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

NODE_ROLES = ("main", "cache")
ROLE_LABELS = {"main": "MAIN_CDN", "cache": "CACHE"}
ROLE_INPUT_ALIASES = {"main_cdn": "main", "main": "main", "cache": "cache"}

PROVISION_READY = "ready"
PROVISION_NOT_STARTED = "not_started"
PROVISION_QUEUED = "queued"
PROVISION_RUNNING = "running"
PROVISION_FAILED = "failed"

PROVISIONING_ACTIONS = frozenset({"provision", "reprovision", "upgrade", "clear-cache"})
STATE_ACTIONS = frozenset({"drain", "undrain", "disable", "enable"})
ALL_ACTIONS = PROVISIONING_ACTIONS | STATE_ACTIONS

CREDENTIAL_PASSWORD = "password"
CREDENTIAL_PRIVATE_KEY = "private_key"
CREDENTIAL_MANAGED_KEY = "managed_key"


class CDNManagementError(ValueError):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    value = _aware(value)
    return value.isoformat() if value else None


# ---------------------------------------------------------------------------
# Encryption helpers (never log plaintext)
# ---------------------------------------------------------------------------


def _require_master_key(settings: Settings) -> str:
    key = (settings.integration_secrets_key or "").strip()
    if not key:
        raise CDNManagementError(
            "INTEGRATION_SECRETS_KEY must be configured before storing credentials"
        )
    return key


def _encrypt_json(value: dict[str, str], settings: Settings) -> bytes:
    try:
        return encrypt_secret(plaintext=json.dumps(value), master_key=_require_master_key(settings))
    except IntegrationSecretsError as exc:
        raise CDNManagementError("Unable to encrypt credentials") from exc


def _decrypt_json(ciphertext: bytes | None, settings: Settings) -> dict[str, str]:
    if not ciphertext:
        return {}
    try:
        raw = decrypt_secret(ciphertext=ciphertext, master_key=_require_master_key(settings))
        parsed = json.loads(raw)
    except (IntegrationSecretsError, json.JSONDecodeError) as exc:
        raise CDNManagementError("Unable to decrypt stored credentials") from exc
    return {str(k): str(v) for k, v in dict(parsed).items()}


# ---------------------------------------------------------------------------
# Storage / R2 settings (IntegrationConfig provider = cloudflare_r2)
# ---------------------------------------------------------------------------


def _storage_row(db: Session) -> IntegrationConfig | None:
    return db.query(IntegrationConfig).filter_by(provider=R2_PROVIDER).one_or_none()


def get_r2(db: Session) -> dict[str, Any]:
    row = _storage_row(db)
    data = dict(row.config_json or {}) if row else {}
    provider = str(data.get("provider") or "cloudflare_r2")
    return {
        "enabled": bool(row.enabled) if row else False,
        "provider": provider,
        "endpoint_url": data.get("endpoint_url", ""),
        "account_id": data.get("account_id"),
        "bucket": data.get("bucket", ""),
        "region": data.get("region", "auto"),
        "object_key_prefix": data.get("object_key_prefix", "ifilm"),
        "credentials_configured": bool(row and row.secret_ciphertext),
        "updated_at": _iso(row.updated_at) if row else None,
        "last_test_at": data.get("last_test_at"),
        "last_test_ok": data.get("last_test_ok"),
        "last_test_reachable": data.get("last_test_reachable"),
        "last_test_bucket_accessible": data.get("last_test_bucket_accessible"),
        "last_test_message": data.get("last_test_message"),
        # Additive fields from other features (e.g. artwork CDN) are preserved untouched.
    }


def resolve_r2_runtime(db: Session, settings: Settings | None = None) -> dict[str, Any] | None:
    """Resolve the private runtime configuration; never use this in an API response."""
    cfg = settings or get_settings()
    row = _storage_row(db)
    if row is None or not row.enabled or not row.secret_ciphertext:
        return None
    credentials = _decrypt_json(row.secret_ciphertext, cfg)
    data = dict(row.config_json or {})
    return {**data, **credentials, "enabled": True}


def _validate_endpoint(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise CDNManagementError("Storage endpoint must be a valid HTTPS URL")
    if parsed.username or parsed.password:
        raise CDNManagementError("Storage endpoint must not embed credentials")
    if parsed.query or parsed.fragment:
        raise CDNManagementError("Storage endpoint must not contain a query or fragment")
    return parsed.geturl()


def update_r2(
    db: Session, admin: AdminUser, payload: dict[str, Any], settings: Settings | None = None
) -> dict[str, Any]:
    cfg = settings or get_settings()
    row = _storage_row(db)
    if row is None:
        row = IntegrationConfig(provider=R2_PROVIDER, enabled=False, config_json={})
    data = dict(row.config_json or {})

    provider = str(payload.get("provider") or data.get("provider") or "cloudflare_r2").strip()
    provider = provider.lower()
    if provider not in STORAGE_PROVIDERS:
        raise CDNManagementError("Provider must be cloudflare_r2 or s3_compatible")
    prefix = str(payload.get("object_key_prefix") or data.get("object_key_prefix") or "ifilm")
    prefix = prefix.strip().strip("/")
    if not KEY_PREFIX_RE.fullmatch(prefix):
        raise CDNManagementError("Object key prefix may contain letters, digits, dot, dash, underscore")

    data.update(
        {
            "provider": provider,
            "endpoint_url": _validate_endpoint(str(payload.get("endpoint_url") or "")),
            "account_id": (payload.get("account_id") or "").strip() or None,
            "bucket": str(payload.get("bucket") or "").strip(),
            "region": str(payload.get("region") or "auto").strip() or "auto",
            "object_key_prefix": prefix,
        }
    )
    if not data["bucket"]:
        raise CDNManagementError("Bucket is required")

    access = (payload.get("access_key_id") or "").strip()
    secret = (payload.get("secret_access_key") or "").strip()
    if bool(access) != bool(secret):
        raise CDNManagementError("Access key and secret key must be supplied together")
    if payload.get("remove_credentials"):
        row.secret_ciphertext = None
        logger.info("cdn_storage_event event=credentials_removed admin_id=%s", admin.id)
    elif access and secret:
        row.secret_ciphertext = _encrypt_json(
            {"access_key_id": access, "secret_access_key": secret}, cfg
        )
        # Credentials changed → previous test result no longer meaningful.
        for key in (
            "last_test_at",
            "last_test_ok",
            "last_test_reachable",
            "last_test_bucket_accessible",
            "last_test_message",
        ):
            data.pop(key, None)
        logger.info("cdn_storage_event event=credentials_replaced admin_id=%s", admin.id)
    # Blank credentials preserve the existing ciphertext.

    row.enabled = bool(payload.get("enabled"))
    if row.enabled and not row.secret_ciphertext:
        raise CDNManagementError("Storage cannot be enabled without stored credentials")
    row.config_json = data
    row.updated_by_admin_id = admin.id
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    logger.info("cdn_storage_event event=settings_updated admin_id=%s", admin.id)
    return get_r2(db)


ProbeFn = Callable[[S3CompatibleConfig], dict[str, Any]]


def test_r2_connection(
    db: Session,
    admin: AdminUser,
    settings: Settings | None = None,
    probe: ProbeFn = probe_s3_connection,
) -> dict[str, Any]:
    """Run a bounded connectivity probe with the stored credentials; persist a summary."""
    cfg = settings or get_settings()
    row = _storage_row(db)
    if row is None or not row.secret_ciphertext:
        raise CDNManagementError("Save storage credentials before testing the connection")
    data = dict(row.config_json or {})
    credentials = _decrypt_json(row.secret_ciphertext, cfg)
    provider = str(data.get("provider") or "cloudflare_r2")
    config = S3CompatibleConfig(
        endpoint_url=str(data.get("endpoint_url") or ""),
        bucket=str(data.get("bucket") or ""),
        region=str(data.get("region") or "auto"),
        access_key_id=credentials.get("access_key_id", ""),
        secret_access_key=credentials.get("secret_access_key", ""),
        force_path_style=provider == "s3_compatible",
        provider_kind=(
            StorageProviderKind.R2 if provider == "cloudflare_r2" else StorageProviderKind.S3_COMPATIBLE
        ),
        role=StorageRole.HOT_CDN,
    )
    result = probe(config)
    tested_at = utcnow().isoformat()
    data.update(
        {
            "last_test_at": tested_at,
            "last_test_ok": bool(result.get("ok")),
            "last_test_reachable": bool(result.get("reachable")),
            "last_test_bucket_accessible": bool(result.get("bucket_accessible")),
            "last_test_message": str(result.get("message") or "")[:500],
        }
    )
    row.config_json = data
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    logger.info(
        "cdn_storage_event event=connection_test admin_id=%s ok=%s reachable=%s bucket=%s",
        admin.id,
        bool(result.get("ok")),
        bool(result.get("reachable")),
        bool(result.get("bucket_accessible")),
    )
    return {
        "ok": bool(result.get("ok")),
        "reachable": bool(result.get("reachable")),
        "bucket_accessible": bool(result.get("bucket_accessible")),
        "endpoint_host": result.get("endpoint_host"),
        "message": str(result.get("message") or ""),
        "tested_at": tested_at,
        "settings": get_r2(db),
    }


# ---------------------------------------------------------------------------
# Managed nodes
# ---------------------------------------------------------------------------


def normalize_role(value: str | None) -> str:
    key = (value or "").strip().lower()
    if key not in ROLE_INPUT_ALIASES:
        raise CDNManagementError("Role must be MAIN_CDN or CACHE")
    return ROLE_INPUT_ALIASES[key]


def validate_host(value: str) -> str:
    host = (value or "").strip().lower().rstrip(".")
    if not host or "/" in host or "://" in host or "@" in host or any(c.isspace() for c in host):
        raise CDNManagementError("Host must be an IP address or hostname")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if not HOSTNAME_RE.fullmatch(host):
            raise CDNManagementError("Host must be an IP address or hostname") from None
        return host
    if (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
    ):
        raise CDNManagementError("Host must be a routable server address")
    return str(address)


def validate_serve_base_url(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CDNManagementError("Serve base URL must be an http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise CDNManagementError("Serve base URL must not contain credentials, query, or fragment")
    return text.rstrip("/")


def validate_host_fingerprint(value: str | None) -> str | None:
    clean = (value or "").strip()
    if not clean:
        return None
    if not HOST_KEY_RE.fullmatch(clean):
        raise CDNManagementError("SSH host key must be an SHA256 fingerprint")
    return clean


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_heartbeat_token(node: ManagedCDNNode) -> str:
    """Issue the node identity token (returned once; stored only as a hash)."""
    raw = secrets.token_urlsafe(32)
    node.heartbeat_token_hash = _hash_token(raw)
    return raw


def verify_heartbeat_token(node: ManagedCDNNode, token: str) -> bool:
    stored_hash = node.heartbeat_token_hash
    if not stored_hash or not token:
        return False
    return hmac.compare_digest(stored_hash, _hash_token(token))


def heartbeat_fresh(node: ManagedCDNNode, *, now: datetime, stale_seconds: int) -> bool:
    ts = _aware(node.last_heartbeat_at)
    if ts is None:
        return False
    return (now - ts).total_seconds() <= float(stale_seconds)


def node_state(node: ManagedCDNNode, *, now: datetime, stale_seconds: int) -> str:
    """Single badge-friendly state used by the admin UI and routing eligibility."""
    if not node.enabled:
        return "disabled"
    if node.provision_status in {PROVISION_QUEUED, PROVISION_RUNNING}:
        return "provisioning"
    if node.provision_status == PROVISION_FAILED:
        return "failed"
    if node.draining:
        return "draining"
    if heartbeat_fresh(node, now=now, stale_seconds=stale_seconds):
        return "online"
    return "offline"


def _node_public(node: ManagedCDNNode, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    now = utcnow()
    stale = int(cfg.cdn_node_heartbeat_stale_seconds)
    hits, misses = int(node.cache_hits or 0), int(node.cache_misses or 0)
    last_hb = _aware(node.last_heartbeat_at)
    limit = int(node.cache_limit_bytes or 0)
    used = int(node.cache_used_bytes or 0)
    return {
        "id": node.id,
        "name": node.name,
        "role": node.role,
        "role_label": ROLE_LABELS.get(node.role, node.role.upper()),
        "host": node.host,
        "ssh_port": node.ssh_port,
        "ssh_username": node.ssh_username,
        "credential_type": node.credential_type,
        "credential_configured": bool(node.credential_ciphertext),
        "managed_key_configured": bool(node.managed_key_ciphertext),
        "managed_key_fingerprint": node.managed_key_fingerprint,
        "ssh_host_key_fingerprint": node.ssh_host_key_fingerprint,
        "observed_host_key_fingerprint": node.observed_host_key_fingerprint,
        "heartbeat_token_configured": bool(node.heartbeat_token_hash),
        "branch": node.branch,
        "location": node.location,
        "notes": node.notes,
        "enabled": node.enabled,
        "draining": node.draining,
        "is_default": node.is_default,
        "priority": int(node.priority or 100),
        "serve_base_url": node.serve_base_url,
        "cache_limit_bytes": node.cache_limit_bytes,
        "storage_limit_bytes": node.cache_limit_bytes,
        "high_watermark_pct": int(node.high_watermark_pct or 90),
        "low_watermark_pct": int(node.low_watermark_pct or 80),
        "disk_total_bytes": node.disk_total_bytes,
        "disk_used_bytes": node.disk_used_bytes,
        "disk_free_bytes": node.disk_free_bytes,
        "cache_used_bytes": node.cache_used_bytes,
        "cache_utilization_pct": round(used * 100 / limit, 2) if limit and used is not None else None,
        "cached_objects": node.cached_objects,
        "cached_titles": node.cached_titles,
        "cache_hits": hits,
        "cache_misses": misses,
        "hit_rate": round(hits * 100 / (hits + misses), 2) if hits + misses else None,
        "bandwidth_bytes": node.bandwidth_bytes,
        "rtt_ms": node.rtt_ms,
        "software_version": node.software_version,
        "os_release": node.os_release,
        "health_status": node.health_status,
        "state": node_state(node, now=now, stale_seconds=stale),
        "online": heartbeat_fresh(node, now=now, stale_seconds=stale),
        "heartbeat_age_seconds": int((now - last_hb).total_seconds()) if last_hb else None,
        "provision_status": node.provision_status,
        "provisioned_at": _iso(node.provisioned_at),
        "last_error": node.last_error,
        "last_error_at": _iso(node.last_error_at),
        "last_ssh_test_at": _iso(node.last_ssh_test_at),
        "last_ssh_test_ok": node.last_ssh_test_ok,
        "last_sync_at": _iso(node.last_sync_at),
        "last_heartbeat_at": _iso(node.last_heartbeat_at),
        "created_at": _iso(node.created_at),
        "updated_at": _iso(node.updated_at),
        # Never: credential_ciphertext, managed_key_ciphertext, heartbeat_token_hash.
    }


def node_public(node: ManagedCDNNode, settings: Settings | None = None) -> dict[str, Any]:
    return _node_public(node, settings)


def list_nodes(db: Session, settings: Settings | None = None) -> list[dict[str, Any]]:
    cfg = settings or get_settings()
    rows = (
        db.query(ManagedCDNNode)
        .order_by(ManagedCDNNode.role.desc(), ManagedCDNNode.priority.asc(), ManagedCDNNode.name)
        .all()
    )
    return [_node_public(n, cfg) for n in rows]


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
) -> tuple[dict[str, Any], str | None]:
    cfg = settings or get_settings()
    created = node is None
    node = node or ManagedCDNNode(created_by_admin_id=admin.id)

    if "role" in payload and payload["role"] is not None:
        node.role = normalize_role(str(payload["role"]))
    if "host" in payload and payload["host"] is not None:
        node.host = validate_host(str(payload["host"]))
    if "serve_base_url" in payload:
        node.serve_base_url = validate_serve_base_url(payload.get("serve_base_url"))
    if "storage_limit_bytes" in payload and payload.get("storage_limit_bytes") is not None:
        payload = {**payload, "cache_limit_bytes": payload["storage_limit_bytes"]}
    for key in (
        "name",
        "ssh_port",
        "ssh_username",
        "credential_type",
        "branch",
        "location",
        "notes",
        "enabled",
        "is_default",
        "priority",
        "cache_limit_bytes",
        "high_watermark_pct",
        "low_watermark_pct",
    ):
        if key in payload and payload[key] is not None:
            setattr(node, key, payload[key])

    username = (node.ssh_username or "").strip()
    if not username or any(c.isspace() for c in username) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
        raise CDNManagementError("SSH username must be a valid POSIX user name")
    node.ssh_username = username
    if node.ssh_port is None or not 1 <= int(node.ssh_port) <= 65535:
        raise CDNManagementError("SSH port must be between 1 and 65535")
    if node.cache_limit_bytes is not None and int(node.cache_limit_bytes) <= 0:
        raise CDNManagementError("Storage limit must be greater than zero")
    if node.role == "cache" and not node.cache_limit_bytes:
        raise CDNManagementError("Cache servers require a storage limit")
    high, low = int(node.high_watermark_pct or 90), int(node.low_watermark_pct or 80)
    if not (1 <= low < high <= 100):
        raise CDNManagementError("Watermarks must satisfy 1 <= low < high <= 100")
    if not 0 <= int(node.priority or 100) <= 100000:
        raise CDNManagementError("Priority must be between 0 and 100000")

    if "ssh_host_key_fingerprint" in payload:
        node.ssh_host_key_fingerprint = validate_host_fingerprint(
            payload.get("ssh_host_key_fingerprint")
        )
    if payload.get("remove_credential"):
        node.credential_ciphertext = None
    elif payload.get("credential"):
        if node.credential_type not in {CREDENTIAL_PASSWORD, CREDENTIAL_PRIVATE_KEY}:
            node.credential_type = CREDENTIAL_PASSWORD
        node.credential_ciphertext = _encrypt_json({"value": str(payload["credential"])}, cfg)
    if not node.credential_ciphertext and not node.managed_key_ciphertext:
        raise CDNManagementError("SSH credential is required")
    if node.is_default and node.role != "main":
        raise CDNManagementError("Only a Main CDN node can be the default")

    heartbeat_token = None
    if created and payload.get("issue_heartbeat_token", True):
        heartbeat_token = issue_heartbeat_token(node)
    db.add(node)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise CDNManagementError("A server with this host already exists") from exc
    if node.is_default:
        db.query(ManagedCDNNode).filter(ManagedCDNNode.id != node.id).update({"is_default": False})
    db.commit()
    db.refresh(node)
    logger.info(
        "cdn_node_event event=%s node_id=%s admin_id=%s",
        "created" if created else "updated",
        node.id,
        admin.id,
    )
    return _node_public(node, cfg), heartbeat_token


def load_bootstrap_credential(node: ManagedCDNNode, settings: Settings) -> str | None:
    """Return the plaintext bootstrap credential for the privileged worker only."""
    return _decrypt_json(node.credential_ciphertext, settings).get("value") or None


def load_managed_private_key(node: ManagedCDNNode, settings: Settings) -> str | None:
    return _decrypt_json(node.managed_key_ciphertext, settings).get("private_key_pem") or None


def store_managed_key(
    node: ManagedCDNNode,
    *,
    private_key_pem: str,
    public_key_line: str,
    fingerprint: str,
    settings: Settings,
) -> None:
    node.managed_key_ciphertext = _encrypt_json({"private_key_pem": private_key_pem}, settings)
    node.managed_key_public = public_key_line.strip()
    node.managed_key_fingerprint = fingerprint


def record_ssh_test(
    db: Session, node: ManagedCDNNode, result: dict[str, Any], settings: Settings | None = None
) -> dict[str, Any]:
    node.last_ssh_test_at = utcnow()
    node.last_ssh_test_ok = bool(result.get("ok"))
    observed = validate_host_fingerprint(result.get("host_key_fingerprint")) if result.get("host_key_fingerprint") else None
    if observed:
        node.observed_host_key_fingerprint = observed
    if result.get("os_release"):
        node.os_release = str(result["os_release"])[:64]
    if result.get("rtt_ms") is not None:
        node.rtt_ms = int(result["rtt_ms"])
    if result.get("disk_total_bytes") is not None:
        node.disk_total_bytes = int(result["disk_total_bytes"])
    if result.get("disk_free_bytes") is not None:
        node.disk_free_bytes = int(result["disk_free_bytes"])
    db.add(node)
    db.commit()
    db.refresh(node)
    return {**result, "node": _node_public(node, settings)}


def record_heartbeat(
    db: Session,
    node: ManagedCDNNode,
    payload: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Persist authenticated node metrics and return the desired state for the node."""
    cfg = settings or get_settings()
    for key in (
        "disk_total_bytes",
        "disk_used_bytes",
        "disk_free_bytes",
        "cache_used_bytes",
        "cached_objects",
        "cached_titles",
        "cache_hits",
        "cache_misses",
        "bandwidth_bytes",
        "rtt_ms",
        "software_version",
        "os_release",
    ):
        if key in payload and payload[key] is not None:
            setattr(node, key, payload[key])
    error = payload.get("last_error")
    if error:
        node.last_error = str(error)[:2000]
        node.last_error_at = utcnow()
    node.health_status = "degraded" if payload.get("degraded") else "online"
    node.last_heartbeat_at = utcnow()
    node.last_sync_at = node.last_heartbeat_at
    db.add(node)
    db.commit()
    db.refresh(node)
    return {
        "ok": True,
        "node_id": node.id,
        "desired": {
            "draining": bool(node.draining),
            "enabled": bool(node.enabled),
            "cache_limit_bytes": node.cache_limit_bytes,
            "high_watermark_pct": int(node.high_watermark_pct or 90),
            "low_watermark_pct": int(node.low_watermark_pct or 80),
        },
        "heartbeat_interval_seconds": 30,
        "server_time": utcnow().isoformat(),
        "node": _node_public(node, cfg),
    }


def apply_state_action(db: Session, admin: AdminUser, node: ManagedCDNNode, action: str) -> dict[str, Any]:
    if action == "drain":
        node.draining = True
    elif action == "undrain":
        node.draining = False
    elif action == "disable":
        node.enabled = False
    elif action == "enable":
        node.enabled = True
    else:
        raise CDNManagementError("Unknown state action")
    db.add(node)
    db.commit()
    db.refresh(node)
    logger.info("cdn_node_event event=%s node_id=%s admin_id=%s", action, node.id, admin.id)
    return _node_public(node)


def _run_public(run: CDNProvisionRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "node_id": run.node_id,
        "action": run.action,
        "status": run.status,
        "step": run.step,
        "attempt": int(run.attempt or 0),
        "error_code": run.error_code,
        "resume_from_step": run.resume_from_step,
        "log": run.log_text,
        "claimed_by": run.claimed_by,
        "claimed_at": _iso(run.claimed_at),
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "created_at": _iso(run.created_at),
    }


def run_public(run: CDNProvisionRun) -> dict[str, Any]:
    return _run_public(run)


def queue_action(
    db: Session, admin: AdminUser, node: ManagedCDNNode, action: str
) -> dict[str, Any]:
    if action not in PROVISIONING_ACTIONS:
        raise CDNManagementError("Unknown provisioning action")
    if not node.ssh_host_key_fingerprint:
        raise CDNManagementError("Pin and confirm the SSH host key before provisioning")
    if not node.credential_ciphertext and not node.managed_key_ciphertext:
        raise CDNManagementError("An SSH credential is required before provisioning")
    if action in {"upgrade", "clear-cache"} and node.provision_status != PROVISION_READY:
        raise CDNManagementError("Provision the server before upgrading or clearing its cache")
    active = (
        db.query(CDNProvisionRun)
        .filter(
            CDNProvisionRun.node_id == node.id,
            CDNProvisionRun.status.in_([PROVISION_QUEUED, PROVISION_RUNNING]),
        )
        .first()
    )
    if active is not None:
        raise CDNManagementError("A provisioning run is already queued or running for this server")
    resume_from: str | None = None
    if action == "provision":
        last_failed = (
            db.query(CDNProvisionRun)
            .filter(
                CDNProvisionRun.node_id == node.id,
                CDNProvisionRun.action.in_(["provision", "reprovision"]),
            )
            .order_by(CDNProvisionRun.created_at.desc())
            .first()
        )
        if last_failed is not None and last_failed.status == PROVISION_FAILED and last_failed.step:
            resume_from = last_failed.step
    run = CDNProvisionRun(
        node_id=node.id,
        action=action,
        status=PROVISION_QUEUED,
        requested_by_admin_id=admin.id,
        resume_from_step=resume_from,
        log_text="Queued. Credentials and secret command output are never recorded.\n",
    )
    node.provision_status = PROVISION_QUEUED
    node.last_error = None
    node.last_error_at = None
    db.add_all([run, node])
    db.commit()
    db.refresh(run)
    logger.info(
        "cdn_node_event event=action_queued action=%s node_id=%s run_id=%s admin_id=%s",
        action,
        node.id,
        run.id,
        admin.id,
    )
    return _run_public(run)


def list_runs(db: Session, node_id: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = (
        db.query(CDNProvisionRun)
        .filter_by(node_id=node_id)
        .order_by(CDNProvisionRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_run_public(r) for r in rows]


def delete_node(db: Session, admin: AdminUser, node: ManagedCDNNode) -> None:
    active = (
        db.query(CDNProvisionRun)
        .filter(
            CDNProvisionRun.node_id == node.id,
            CDNProvisionRun.status == PROVISION_RUNNING,
        )
        .first()
    )
    if active is not None:
        raise CDNManagementError("Wait for the running provisioning job to finish before deleting")
    db.delete(node)
    db.commit()
    logger.info("cdn_node_event event=deleted node_id=%s admin_id=%s", node.id, admin.id)


# ---------------------------------------------------------------------------
# Prefix routes
# ---------------------------------------------------------------------------


def validate_cidr(cidr: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    try:
        return ipaddress.ip_network(cidr.strip(), strict=True)
    except ValueError as exc:
        raise CDNManagementError("CIDR must be a canonical IPv4 or IPv6 network") from exc


def route_public(route: CDNPrefixRoute, node: ManagedCDNNode | None = None) -> dict[str, Any]:
    return {
        "id": route.id,
        "cidr": route.cidr,
        "prefix_length": route.prefix_length,
        "node_id": route.node_id,
        "node_name": node.name if node else None,
        "node_role": node.role if node else None,
        "priority": route.priority,
        "enabled": route.enabled,
        "notes": route.notes,
        "created_at": _iso(route.created_at),
        "updated_at": _iso(route.updated_at),
    }


def save_route(
    db: Session, payload: dict[str, Any], route: CDNPrefixRoute | None = None
) -> dict[str, Any]:
    network = validate_cidr(str(payload["cidr"]))
    node = get_node(db, str(payload["node_id"]))
    route = route or CDNPrefixRoute()
    route.cidr, route.prefix_length, route.node_id = str(network), network.prefixlen, node.id
    route.priority = int(payload.get("priority", 100))
    route.enabled = bool(payload.get("enabled", True))
    if "notes" in payload:
        route.notes = (payload.get("notes") or "").strip() or None
    db.add(route)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise CDNManagementError("A routing rule for this CIDR already exists") from exc
    db.refresh(route)
    return route_public(route, node)


def list_routes(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(CDNPrefixRoute, ManagedCDNNode)
        .join(ManagedCDNNode)
        .order_by(CDNPrefixRoute.prefix_length.desc(), CDNPrefixRoute.priority.asc())
        .all()
    )
    return [route_public(r, n) for r, n in rows]


def select_node(db: Session, client_ip: str, settings: Settings | None = None) -> dict[str, Any]:
    """Backward-compatible wrapper around the CDN-P1 routing engine."""
    from app.services.cdn_routing import evaluate_route

    decision = evaluate_route(db, client_ip, settings=settings)
    node = decision.get("selected")
    return {
        "mode": node["role"] if node else "central",
        "reason": decision["reason"],
        "matched_cidr": decision["matched_cidr"],
        "node": node,
        "chain": decision["chain"],
        "client_ip": decision["client_ip"],
        "central_fallback": True,
    }


# ---------------------------------------------------------------------------
# Overview / status
# ---------------------------------------------------------------------------


def status_flags(settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    return {
        "enable_cdn_node_api": bool(cfg.enable_cdn_node_api),
        "enable_cdn_provisioning": bool(cfg.enable_cdn_provisioning),
        "enable_cdn_edge_routing": bool(cfg.enable_cdn_edge_routing),
        "edge_routing_phase": "CDN-P2 (not enabled)",
        "customer_playback_route": "/api/stream/{token}/... (central)",
        "heartbeat_stale_seconds": int(cfg.cdn_node_heartbeat_stale_seconds),
        "integration_secrets_configured": bool((cfg.integration_secrets_key or "").strip()),
        "edge_grant_public_key_configured": bool((cfg.edge_grant_public_key_pem or "").strip()),
        "legacy_cdn_sync_enabled": bool(cfg.enable_cdn_sync),
    }


def overview(db: Session, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    nodes = [_node_public(n, cfg) for n in db.query(ManagedCDNNode).all()]
    now = utcnow()
    since = now - timedelta(hours=24)
    failures = (
        db.query(CDNProvisionRun, ManagedCDNNode)
        .join(ManagedCDNNode)
        .filter(CDNProvisionRun.status == PROVISION_FAILED, CDNProvisionRun.created_at >= since)
        .order_by(CDNProvisionRun.created_at.desc())
        .limit(10)
        .all()
    )
    hits = sum(int(n["cache_hits"]) for n in nodes)
    misses = sum(int(n["cache_misses"]) for n in nodes)
    mains = [n for n in nodes if n["role"] == "main"]
    default_main = next((n for n in mains if n["is_default"]), None)
    return {
        "generated_at": now.isoformat(),
        "flags": status_flags(cfg),
        "totals": {
            "nodes": len(nodes),
            "online": sum(1 for n in nodes if n["state"] == "online"),
            "offline": sum(1 for n in nodes if n["state"] == "offline"),
            "draining": sum(1 for n in nodes if n["state"] == "draining"),
            "provisioning": sum(1 for n in nodes if n["state"] == "provisioning"),
            "failed": sum(1 for n in nodes if n["state"] == "failed"),
            "disabled": sum(1 for n in nodes if n["state"] == "disabled"),
            "main_nodes": len(mains),
            "cache_nodes": sum(1 for n in nodes if n["role"] == "cache"),
            "routes": db.query(CDNPrefixRoute).count(),
            "routes_enabled": db.query(CDNPrefixRoute).filter_by(enabled=True).count(),
        },
        "main_cdn": {
            "default_node": default_main,
            "status": default_main["state"] if default_main else "not_configured",
            "secondary_online": sum(
                1 for n in mains if not n["is_default"] and n["state"] == "online"
            ),
        },
        "storage": {
            "disk_total_bytes": sum(int(n["disk_total_bytes"] or 0) for n in nodes),
            "disk_used_bytes": sum(int(n["disk_used_bytes"] or 0) for n in nodes),
            "disk_free_bytes": sum(int(n["disk_free_bytes"] or 0) for n in nodes),
            "cache_limit_bytes": sum(int(n["cache_limit_bytes"] or 0) for n in nodes),
            "cache_used_bytes": sum(int(n["cache_used_bytes"] or 0) for n in nodes),
        },
        "cache": {
            "hits": hits,
            "misses": misses,
            "hit_rate": round(hits * 100 / (hits + misses), 2) if hits + misses else None,
            "bandwidth_bytes": sum(int(n["bandwidth_bytes"] or 0) for n in nodes),
        },
        "recent_provisioning_failures": [
            {**_run_public(run), "node_name": node.name} for run, node in failures
        ],
        "central_fallback": "always",
    }
