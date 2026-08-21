"""Versioned non-secret one-node staging inventory (Phase 9).

Schema: ifilm.branch_node.staging_inventory.v1

Private keys, PEM bodies, live endpoints with credentials, and mutable image
tags are forbidden. Unknown fields are rejected.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_NODE_ID_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{1,62}[a-z0-9])$|^[a-z0-9]{3}$")
_SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")
_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))*$"
)
_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "private_key",
        "client_key_pem",
        "certificate_pem",
        "ca_pem",
        "password",
        "secret",
        "token",
        "api_key",
    }
)


class ModelForbidExtra(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OriginEndpoint(ModelForbidExtra):
    """Exactly one fixed HTTPS origin (hostname + port)."""

    host: str
    port: int = Field(ge=1, le=65535)
    # Operator-reviewed pinned A/AAAA evidence (required for plan success).
    pinned_resolved_ipv4: str
    reviewed_dns_evidence_id: str = Field(min_length=8, max_length=128)

    @field_validator("host")
    @classmethod
    def _host(cls, value: str) -> str:
        text = (value or "").strip().lower()
        if not text:
            raise ValueError("origin host required")
        if "*" in text or text.startswith("."):
            raise ValueError("wildcard hosts forbidden")
        if _IPV4_RE.match(text) or ":" in text:
            raise ValueError("origin host must be a DNS hostname, not a raw IP")
        if not _HOSTNAME_RE.match(text):
            raise ValueError("invalid origin hostname")
        if text in {"localhost", "metadata.google.internal"}:
            raise ValueError("forbidden origin host")
        return text

    @field_validator("pinned_resolved_ipv4")
    @classmethod
    def _pin(cls, value: str) -> str:
        text = (value or "").strip()
        if not _IPV4_RE.match(text):
            raise ValueError("pinned_resolved_ipv4 must be an IPv4 literal")
        parts = [int(p) for p in text.split(".")]
        if any(p < 0 or p > 255 for p in parts):
            raise ValueError("invalid IPv4")
        # Reject ambiguous / unsafe classes for staging egress pin evidence.
        if parts[0] == 0 or parts[0] == 127 or parts[0] >= 224:
            raise ValueError("pinned IP class not allowed for staging egress evidence")
        if parts[0] == 169 and parts[1] == 254:
            raise ValueError("link-local pin forbidden")
        return text


class TrustFingerprints(ModelForbidExtra):
    mtls_ca_bundle_sha256: str
    mtls_client_cert_sha256: str
    edge_grant_public_key_sha256: str

    @field_validator(
        "mtls_ca_bundle_sha256",
        "mtls_client_cert_sha256",
        "edge_grant_public_key_sha256",
    )
    @classmethod
    def _fp(cls, value: str) -> str:
        text = (value or "").strip().lower()
        if not _SHA256_HEX.match(text):
            raise ValueError("fingerprint must be 64 lowercase hex chars")
        return text


class CacheVolumeSpec(ModelForbidExtra):
    """Dedicated cache device/path — never system roots."""

    device_or_path: str
    mount_path: str = "/var/cache/ifilm-branch"
    high_watermark_bytes: int = Field(ge=1_000_000, le=10_000_000_000_000)
    low_watermark_bytes: int = Field(ge=1_000_000, le=10_000_000_000_000)
    min_free_bytes: int = Field(ge=1_000_000, le=10_000_000_000_000)

    @field_validator("device_or_path", "mount_path")
    @classmethod
    def _paths(cls, value: str) -> str:
        text = (value or "").strip()
        if not text.startswith("/"):
            raise ValueError("absolute path required")
        forbidden = {"/", "/etc", "/var", "/usr", "/home", "/root", "/tmp", "/boot", "/dev"}
        if text.rstrip("/") in forbidden or text in forbidden:
            raise ValueError("cache path must be a dedicated non-system root")
        if ".." in text.split("/"):
            raise ValueError("path traversal forbidden")
        return text

    @model_validator(mode="after")
    def _watermarks(self) -> CacheVolumeSpec:
        if self.low_watermark_bytes >= self.high_watermark_bytes:
            raise ValueError("low_watermark_bytes must be < high_watermark_bytes")
        if self.min_free_bytes > self.low_watermark_bytes:
            raise ValueError("min_free_bytes must be <= low_watermark_bytes")
        return self


class CapacityLimits(ModelForbidExtra):
    cpus: str = "1.0"
    memory_mb: int = Field(default=512, ge=128, le=65536)
    pids: int = Field(default=256, ge=32, le=4096)
    nofile_soft: int = Field(default=1024, ge=64, le=65536)
    nofile_hard: int = Field(default=2048, ge=64, le=65536)
    max_object_bytes: int = Field(default=67_108_864, ge=1024, le=512 * 1024 * 1024)
    max_concurrent_fills: int = Field(default=4, ge=1, le=64)


class ImageRef(ModelForbidExtra):
    """Immutable image reference — digest required, mutable tags rejected."""

    repository: str
    digest: str
    sbom_ref: str = ""
    provenance_ref: str = ""

    @field_validator("repository")
    @classmethod
    def _repo(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("repository required")
        if "@" in text:
            raise ValueError("put digest in digest field, not repository")
        last = text.split("/")[-1]
        if ":" in last:
            raise ValueError("mutable image tags forbidden; use digest field")
        if not re.match(r"^[a-z0-9._/-]+$", text):
            raise ValueError("invalid repository")
        return text

    @field_validator("digest")
    @classmethod
    def _digest(cls, value: str) -> str:
        text = (value or "").strip().lower()
        if not _DIGEST_RE.match(text):
            raise ValueError("image digest must be sha256:<64 hex>")
        return text

    @property
    def pinned_ref(self) -> str:
        return f"{self.repository}@{self.digest}"


class OperatorApproval(ModelForbidExtra):
    record_id: str = Field(min_length=8, max_length=128)
    approver_role: str = Field(min_length=2, max_length=64)
    noted_at_utc: str = ""


class StagingInventoryV1(ModelForbidExtra):
    """Exactly one branch node + one fixed mTLS origin for staging-candidate."""

    schema_version: Literal["ifilm.branch_node.staging_inventory.v1"] = (
        "ifilm.branch_node.staging_inventory.v1"
    )
    environment: Literal["staging-candidate"]
    node_id: str
    site_id: str
    image: ImageRef
    origin: OriginEndpoint
    trust: TrustFingerprints
    cache: CacheVolumeSpec
    capacity: CapacityLimits = Field(default_factory=CapacityLimits)
    operator_approval: OperatorApproval
    # Mount path placeholders only — never PEM contents.
    ca_bundle_mount_path: str = "/run/ifilm/certs/ca-bundle.pem"
    client_cert_mount_path: str = "/run/ifilm/certs/client.crt"
    client_key_mount_path: str = "/run/ifilm/certs/client.key"
    edge_grant_public_key_mount_path: str = "/run/ifilm/certs/edge-grant-public.pem"
    bind_host: Literal["127.0.0.1"] = "127.0.0.1"
    run_as_uid: Literal[10001] = 10001
    run_as_gid: Literal[10001] = 10001
    client_redirect_active: Literal[False] = False
    live_pilot_ready: Literal[False] = False
    management_access_placeholder: str = Field(
        default="REQUIRED:OPERATOR_MGMT_SOURCE_CIDR",
        min_length=8,
        max_length=128,
    )
    dns_resolver_placeholders: list[str] = Field(
        default_factory=lambda: ["REQUIRED:DNS_RESOLVER_IP"]
    )
    notes: str = ""

    @field_validator("node_id", "site_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        text = (value or "").strip().lower()
        if not _NODE_ID_RE.match(text):
            raise ValueError("invalid node_id/site_id")
        return text

    @field_validator(
        "ca_bundle_mount_path",
        "client_cert_mount_path",
        "client_key_mount_path",
        "edge_grant_public_key_mount_path",
    )
    @classmethod
    def _mounts(cls, value: str) -> str:
        text = (value or "").strip()
        if not text.startswith("/run/ifilm/"):
            raise ValueError("cert mounts must be under /run/ifilm/")
        return text

    @field_validator("dns_resolver_placeholders")
    @classmethod
    def _resolvers(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("at least one DNS resolver placeholder required")
        for item in value:
            if not str(item).strip():
                raise ValueError("empty DNS resolver placeholder")
        return value

    def to_public_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        blob = json.dumps(data, sort_keys=True)
        if "PRIVATE KEY" in blob or "BEGIN CERTIFICATE" in blob:
            raise ValueError("inventory must not embed certificate or key PEM")
        return data


def _reject_secret_keys(raw: Any) -> None:
    if isinstance(raw, dict):
        for key, val in raw.items():
            if str(key).lower() in _FORBIDDEN_SECRET_KEYS:
                raise ValueError(f"forbidden secret field in inventory: {key}")
            _reject_secret_keys(val)
    elif isinstance(raw, list):
        for item in raw:
            _reject_secret_keys(item)


def reject_credential_urls(text: str) -> None:
    """Fail closed if a URL-like string embeds credentials/query/fragment."""
    for token in text.split():
        if "://" not in token:
            continue
        parsed = urlparse(token)
        if parsed.username or parsed.password:
            raise ValueError("URLs with credentials forbidden")
        if parsed.query or parsed.fragment:
            raise ValueError("URLs with query/fragment forbidden")


def load_staging_inventory(path: Path) -> StagingInventoryV1:
    raw = json.loads(path.read_text(encoding="utf-8"))
    _reject_secret_keys(raw)
    if isinstance(raw, dict):
        env = raw.get("environment")
        if env in {"production", "prod"}:
            raise ValueError("production environment forbidden in Phase 9 inventory")
        if env != "staging-candidate":
            raise ValueError("environment must be staging-candidate")
    inv = StagingInventoryV1.model_validate(raw)
    reject_credential_urls(json.dumps(inv.to_public_dict()))
    return inv


def write_staging_inventory(path: Path, inventory: StagingInventoryV1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(inventory.to_public_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def example_inventory_dict() -> dict[str, Any]:
    """Placeholder example — no real endpoints/secrets."""
    return {
        "schema_version": "ifilm.branch_node.staging_inventory.v1",
        "environment": "staging-candidate",
        "node_id": "staging-node-1",
        "site_id": "staging-site",
        "image": {
            "repository": "ghcr.io/example/ifilm-branch-cache-lab",
            "digest": "sha256:" + ("a" * 64),
            "sbom_ref": "placeholder:sbom-spdx-ref",
            "provenance_ref": "placeholder:provenance-attestation-ref",
        },
        "origin": {
            "host": "origin.staging-candidate.example.internal",
            "port": 8443,
            "pinned_resolved_ipv4": "10.50.1.10",
            "reviewed_dns_evidence_id": "dns-evidence-placeholder-001",
        },
        "trust": {
            "mtls_ca_bundle_sha256": "b" * 64,
            "mtls_client_cert_sha256": "c" * 64,
            "edge_grant_public_key_sha256": "d" * 64,
        },
        "cache": {
            "device_or_path": "/var/lib/ifilm-branch-staging-cache",
            "mount_path": "/var/cache/ifilm-branch",
            "high_watermark_bytes": 50_000_000_000,
            "low_watermark_bytes": 40_000_000_000,
            "min_free_bytes": 1_000_000_000,
        },
        "capacity": {
            "cpus": "1.0",
            "memory_mb": 512,
            "pids": 256,
            "nofile_soft": 1024,
            "nofile_hard": 2048,
            "max_object_bytes": 67_108_864,
            "max_concurrent_fills": 4,
        },
        "operator_approval": {
            "record_id": "approval-placeholder-001",
            "approver_role": "staging-owner",
            "noted_at_utc": "1970-01-01T00:00:00Z",
        },
        "client_redirect_active": False,
        "live_pilot_ready": False,
        "management_access_placeholder": "REQUIRED:OPERATOR_MGMT_SOURCE_CIDR",
        "dns_resolver_placeholders": ["REQUIRED:DNS_RESOLVER_IP"],
        "notes": "Phase 9 offline example — replace placeholders before any live review.",
    }
