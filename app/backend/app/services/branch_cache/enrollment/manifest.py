"""Non-secret branch-node enrollment / config manifest (Phase 8).

Private keys and certificate PEMs are NEVER part of this document — only
fingerprints, public trust references, allowlists, and resource limits.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

_NODE_ID_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{1,62}[a-z0-9])$|^[a-z0-9]{3}$")
_SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")


class OriginAllowlistEntry(BaseModel):
    """Single fixed HTTPS origin (host:port + optional path prefix)."""

    https_base_url: str
    host_fingerprint_note: str = ""


class PublicTrustRef(BaseModel):
    """Public trust material references (paths or fingerprints only)."""

    edge_grant_public_key_fingerprint_sha256: str
    edge_grant_key_id: str
    mtls_ca_bundle_fingerprint_sha256: str
    mtls_client_cert_fingerprint_sha256: str = ""
    # Mount paths expected at runtime — never contain PEM bodies in the manifest.
    ca_bundle_mount_path: str = "/run/ifilm/certs/ca-bundle.pem"
    client_cert_mount_path: str = "/run/ifilm/certs/client.crt"
    client_key_mount_path: str = "/run/ifilm/certs/client.key"
    edge_grant_public_key_mount_path: str = "/run/ifilm/certs/edge-grant-public.pem"

    @field_validator(
        "edge_grant_public_key_fingerprint_sha256",
        "mtls_ca_bundle_fingerprint_sha256",
        "mtls_client_cert_fingerprint_sha256",
        mode="before",
    )
    @classmethod
    def _hex_fp(cls, value: Any) -> Any:
        if value in ("", None):
            return value or ""
        text = str(value).strip().lower()
        if not _SHA256_HEX.match(text):
            raise ValueError("fingerprint must be 64 lowercase hex chars")
        return text


class ResourceLimits(BaseModel):
    max_concurrent_fills: int = Field(default=4, ge=1, le=64)
    max_object_bytes: int = Field(default=67_108_864, ge=1024, le=512 * 1024 * 1024)
    connect_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    read_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    high_watermark_bytes: int = Field(default=50_000_000_000, ge=1_000_000)
    low_watermark_bytes: int = Field(default=40_000_000_000, ge=1_000_000)
    min_free_bytes: int = Field(default=1_000_000_000, ge=1_000_000)


class BranchNodeEnrollmentManifest(BaseModel):
    """Versioned, non-secret node configuration contract."""

    schema_version: Literal["ifilm.branch_node.enrollment.v1"] = "ifilm.branch_node.enrollment.v1"
    node_id: str
    site_id: str
    environment: Literal["lab", "development", "staging-candidate", "test"]
    origin_allowlist: list[OriginAllowlistEntry]
    public_trust: PublicTrustRef
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    client_redirect_active: Literal[False] = False
    live_pilot_ready: Literal[False] = False
    notes: str = ""

    @field_validator("node_id")
    @classmethod
    def _node(cls, value: str) -> str:
        text = (value or "").strip().lower()
        if not _NODE_ID_RE.match(text):
            raise ValueError("invalid node_id")
        return text

    @field_validator("origin_allowlist")
    @classmethod
    def _one_origin(cls, value: list[OriginAllowlistEntry]) -> list[OriginAllowlistEntry]:
        if len(value) != 1:
            raise ValueError("exactly one origin allowlist entry required in Phase 8")
        return value

    def to_public_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        # Belt-and-suspenders: strip anything that looks like PEM.
        blob = json.dumps(data)
        if "PRIVATE KEY" in blob or "BEGIN CERTIFICATE" in blob:
            raise ValueError("manifest must not embed certificate or key PEM")
        return data


def load_enrollment_manifest(path: Path) -> BranchNodeEnrollmentManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        for key in ("private_key", "client_key_pem", "certificate_pem", "ca_pem"):
            if key in raw:
                raise ValueError(f"forbidden secret field in manifest: {key}")
    return BranchNodeEnrollmentManifest.model_validate(raw)


def write_enrollment_manifest(path: Path, manifest: BranchNodeEnrollmentManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(manifest.to_public_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


ROTATION_GUIDANCE = """
Atomic certificate rotation (operator):
1. Stage new CA/client cert+key beside live mounts (*.next).
2. Verify fingerprints match the enrollment manifest update.
3. Atomically rename *.next → live paths (or update bind mounts + recreate).
4. Restart branch-cache with drain first; confirm mTLS preflight.
5. Keep previous material as *.prev for one rollback window, then shred.
Never commit, log, or API-return private keys. App does not generate keys.
"""
