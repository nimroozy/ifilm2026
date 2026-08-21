"""Read-only preflight / plan for one-node staging (Phase 9).

Never modifies the host. Host facts are injected for offline/unit tests.
Fails closed when required deployment inputs are absent or incomplete.

Certificate roles are split:
- Origin *server* cert evidence (SAN must exactly include inventory.origin.host)
- Client cert (clientAuth EKU, fingerprint, validity, key match/perms, expected identity)
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.branch_cache.deploy.inventory import (
    StagingInventoryV1,
    is_unreviewed_placeholder,
)
from app.services.branch_cache.ops.node_health import CheckResult


@dataclass(frozen=True)
class CertMaterialFact:
    """Public metadata only — never PEM bodies."""

    path: str
    exists: bool
    is_symlink: bool
    mode_bits: int
    sha256_hex: str
    not_after_utc: str
    san_dns: tuple[str, ...]
    has_client_auth_eku: bool = False
    has_server_auth_eku: bool = False
    subject_cn: str = ""


@dataclass(frozen=True)
class HostFacts:
    """Injected snapshot of host state for offline plan evaluation."""

    os_name: str = "linux"
    kernel: str = "6.1.0"
    time_sync_ok: bool = True
    free_disk_bytes: int = 5_000_000_000
    filesystem_owner_uid: int = 10001
    filesystem_owner_gid: int = 10001
    expected_uid: int = 10001
    fd_limit: int = 2048
    pid_limit: int = 256
    memory_mb: int = 2048
    cpu_count: int = 2
    resolved_origin_ips: tuple[str, ...] = ()
    dns_resolution_stable: bool = True
    ca: CertMaterialFact | None = None
    # Verified mTLS preflight evidence for the *origin server* leaf certificate.
    origin_server_cert: CertMaterialFact | None = None
    client_cert: CertMaterialFact | None = None
    client_key_mode_bits: int = 0o600
    client_key_exists: bool = False
    client_key_matches_cert: bool = False
    # Observed client identity (exact DNS SAN or CN) from client cert material.
    observed_client_identity: str = ""
    edge_grant_public_sha256: str = ""
    image_digest_present: bool = True
    # Concrete reviewed refs only — placeholder strings must not flip these true.
    sbom_ref_reviewed: str = ""
    provenance_ref_reviewed: str = ""
    manifest_signature: str = ""
    feature_flags: dict[str, bool] = field(
        default_factory=lambda: {
            "ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE": False,
            "ENABLE_BRANCH_CACHE_ONE_NODE_STAGING_DEPLOY": False,
            "ENABLE_BRANCH_CACHE_HTTP_SERVICE": False,
        }
    )
    rollback_prior_digest_recorded: bool = True
    forensic_dir_writable: bool = True
    clock_skew_seconds: int = 0


def _check(name: str, ok: bool, detail: str = "ok") -> CheckResult:
    return CheckResult(name, ok, detail if ok else detail)


def _norm_dns(value: str) -> str:
    return (value or "").strip().lower().rstrip(".")


def _cert_not_after_ok(
    fact: CertMaterialFact, now: datetime, *, min_days: int = 7
) -> tuple[bool, str]:
    try:
        not_after = datetime.fromisoformat(fact.not_after_utc.replace("Z", "+00:00"))
    except ValueError:
        return False, "invalid_not_after"
    remaining = (not_after - now).days
    if remaining < min_days:
        return False, "cert_expiring_soon"
    return True, "ok"


def evaluate_preflight(
    inventory: StagingInventoryV1,
    *,
    host: HostFacts,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Produce a go/no-go plan report. Read-only — no host mutation."""
    now = now or datetime.now(tz=UTC)
    checks: list[CheckResult] = []

    checks.append(
        _check("environment_staging_candidate", inventory.environment == "staging-candidate")
    )
    checks.append(_check("live_pilot_ready_false", inventory.live_pilot_ready is False))
    checks.append(_check("client_redirect_active_false", inventory.client_redirect_active is False))
    checks.append(_check("bind_loopback_only", inventory.bind_host == "127.0.0.1"))
    checks.append(
        _check("non_root_uid", inventory.run_as_uid == 10001 and inventory.run_as_gid == 10001)
    )
    checks.append(_check("immutable_image_digest", inventory.image.digest.startswith("sha256:")))

    # Explicit placeholder fields on the inventory fail readiness (non-empty ≠ concrete).
    placeholders = inventory.placeholder_fields()
    checks.append(
        _check(
            "inventory_placeholders_absent",
            not placeholders,
            "ok" if not placeholders else "placeholders:" + ",".join(placeholders),
        )
    )
    checks.append(
        _check(
            "operator_approval_record",
            not is_unreviewed_placeholder(inventory.operator_approval.record_id),
            "ok"
            if not is_unreviewed_placeholder(inventory.operator_approval.record_id)
            else "approval_placeholder_or_missing",
        )
    )

    # OS / capacity
    checks.append(_check("os_linux", host.os_name.lower().startswith("linux"), host.os_name))
    checks.append(_check("kernel_present", bool(host.kernel)))
    checks.append(
        _check("time_sync", host.time_sync_ok, "ok" if host.time_sync_ok else "time_sync_failed")
    )
    checks.append(
        _check(
            "clock_skew",
            abs(int(host.clock_skew_seconds)) <= 60,
            "ok" if abs(int(host.clock_skew_seconds)) <= 60 else "clock_skew",
        )
    )
    checks.append(
        _check(
            "free_disk",
            int(host.free_disk_bytes) >= int(inventory.cache.min_free_bytes),
            "ok"
            if int(host.free_disk_bytes) >= int(inventory.cache.min_free_bytes)
            else "insufficient_disk",
        )
    )
    checks.append(
        _check(
            "filesystem_ownership_uid",
            int(host.filesystem_owner_uid) == int(inventory.run_as_uid),
            "ok" if host.filesystem_owner_uid == inventory.run_as_uid else "uid_mismatch",
        )
    )
    checks.append(
        _check(
            "fd_limit",
            int(host.fd_limit) >= int(inventory.capacity.nofile_soft),
            "ok" if host.fd_limit >= inventory.capacity.nofile_soft else "fd_limit_low",
        )
    )
    checks.append(
        _check(
            "pid_limit",
            int(host.pid_limit) >= int(inventory.capacity.pids),
            "ok" if host.pid_limit >= inventory.capacity.pids else "pid_limit_low",
        )
    )
    checks.append(
        _check(
            "memory",
            int(host.memory_mb) >= int(inventory.capacity.memory_mb),
            "ok" if host.memory_mb >= inventory.capacity.memory_mb else "memory_low",
        )
    )
    checks.append(_check("cpu", int(host.cpu_count) >= 1))

    # CA bundle
    if host.ca is None:
        checks.append(_check("ca_material", False, "ca_facts_absent"))
    else:
        checks.append(_check("ca_exists", host.ca.exists and not host.ca.is_symlink))
        checks.append(
            _check(
                "ca_fingerprint",
                host.ca.sha256_hex == inventory.trust.mtls_ca_bundle_sha256,
                "ok"
                if host.ca.sha256_hex == inventory.trust.mtls_ca_bundle_sha256
                else "ca_fp_mismatch",
            )
        )

    # Origin *server* certificate evidence (from verified mTLS preflight) — SAN exact match.
    origin_host = _norm_dns(inventory.origin.host)
    if host.origin_server_cert is None:
        checks.append(_check("origin_server_cert_material", False, "origin_server_cert_absent"))
    else:
        osc = host.origin_server_cert
        checks.append(_check("origin_server_cert_exists", osc.exists and not osc.is_symlink))
        checks.append(
            _check(
                "origin_server_cert_fingerprint",
                osc.sha256_hex == inventory.trust.mtls_origin_server_cert_sha256,
                "ok"
                if osc.sha256_hex == inventory.trust.mtls_origin_server_cert_sha256
                else "origin_server_fp_mismatch",
            )
        )
        checks.append(
            _check(
                "origin_server_cert_eku",
                osc.has_server_auth_eku,
                "ok" if osc.has_server_auth_eku else "missing_server_auth_eku",
            )
        )
        sans = tuple(_norm_dns(s) for s in osc.san_dns)
        if not sans:
            checks.append(_check("origin_server_san_exact", False, "origin_san_missing"))
        elif origin_host not in sans:
            # Non-empty but wrong/unrelated SAN must fail closed — never "any SAN present".
            checks.append(_check("origin_server_san_exact", False, "origin_san_mismatch"))
        else:
            checks.append(_check("origin_server_san_exact", True, "ok"))
        exp_ok, exp_detail = _cert_not_after_ok(osc, now)
        checks.append(_check("origin_server_cert_expiry", exp_ok, exp_detail))

    # Client certificate — identity is NOT the origin host.
    if host.client_cert is None:
        checks.append(_check("client_cert_material", False, "client_cert_facts_absent"))
    else:
        cc = host.client_cert
        checks.append(_check("client_cert_exists", cc.exists and not cc.is_symlink))
        checks.append(
            _check(
                "client_cert_fingerprint",
                cc.sha256_hex == inventory.trust.mtls_client_cert_sha256,
                "ok"
                if cc.sha256_hex == inventory.trust.mtls_client_cert_sha256
                else "client_fp_mismatch",
            )
        )
        checks.append(
            _check(
                "client_cert_eku",
                cc.has_client_auth_eku,
                "ok" if cc.has_client_auth_eku else "missing_client_auth_eku",
            )
        )
        exp_ok, exp_detail = _cert_not_after_ok(cc, now)
        checks.append(_check("client_cert_expiry", exp_ok, exp_detail))

        expected_id = _norm_dns(inventory.expected_client_identity)
        observed = _norm_dns(host.observed_client_identity)
        client_sans = {_norm_dns(s) for s in cc.san_dns}
        subject = _norm_dns(cc.subject_cn)
        identity_candidates = set(client_sans)
        if subject:
            identity_candidates.add(subject)
        if observed:
            identity_candidates.add(observed)
        identity_ok = expected_id in identity_candidates and expected_id != origin_host
        checks.append(
            _check(
                "client_identity_match",
                identity_ok,
                "ok" if identity_ok else "client_identity_mismatch",
            )
        )
        # Client must not present the origin hostname as its identity.
        checks.append(
            _check(
                "client_identity_not_origin",
                origin_host not in identity_candidates,
                "ok" if origin_host not in identity_candidates else "client_identity_is_origin",
            )
        )

    checks.append(
        _check(
            "client_key_perms",
            host.client_key_exists and (host.client_key_mode_bits & 0o077) == 0,
            "ok"
            if host.client_key_exists and (host.client_key_mode_bits & 0o077) == 0
            else "key_perms",
        )
    )
    checks.append(
        _check(
            "client_key_matches_cert",
            bool(host.client_key_matches_cert),
            "ok" if host.client_key_matches_cert else "key_cert_mismatch",
        )
    )
    checks.append(
        _check(
            "edge_grant_public_fingerprint",
            host.edge_grant_public_sha256 == inventory.trust.edge_grant_public_key_sha256,
            "ok"
            if host.edge_grant_public_sha256 == inventory.trust.edge_grant_public_key_sha256
            else "edge_grant_fp_mismatch",
        )
    )

    # DNS / origin pin — detect rebinding / multiple resolutions
    resolved = tuple(host.resolved_origin_ips)
    checks.append(
        _check(
            "origin_dns_stable",
            bool(host.dns_resolution_stable) and len(set(resolved)) <= 1,
            "ok"
            if host.dns_resolution_stable and len(set(resolved)) <= 1
            else "dns_rebinding_or_flap",
        )
    )
    if not resolved:
        checks.append(_check("origin_dns_resolved", False, "resolution_absent_fail_closed"))
    else:
        pin_ok = resolved[0] == inventory.origin.pinned_resolved_ipv4 and len(set(resolved)) == 1
        checks.append(
            _check(
                "origin_ip_pin_match",
                pin_ok,
                "ok" if pin_ok else "pin_mismatch_or_multi_a",
            )
        )

    checks.append(_check("image_digest_ref", host.image_digest_present))

    # SBOM / provenance / signature — inventory and host evidence must both be concrete.
    sbom_inventory_ok = not is_unreviewed_placeholder(inventory.image.sbom_ref)
    sbom_host_ok = not is_unreviewed_placeholder(host.sbom_ref_reviewed)
    sbom_match = (
        sbom_inventory_ok
        and sbom_host_ok
        and host.sbom_ref_reviewed.strip() == inventory.image.sbom_ref.strip()
    )
    checks.append(
        _check(
            "sbom_ref_concrete",
            sbom_match,
            "ok" if sbom_match else "sbom_placeholder_or_mismatch",
        )
    )

    prov_inventory_ok = not is_unreviewed_placeholder(inventory.image.provenance_ref)
    prov_host_ok = not is_unreviewed_placeholder(host.provenance_ref_reviewed)
    prov_match = (
        prov_inventory_ok
        and prov_host_ok
        and host.provenance_ref_reviewed.strip() == inventory.image.provenance_ref.strip()
    )
    checks.append(
        _check(
            "provenance_ref_concrete",
            prov_match,
            "ok" if prov_match else "provenance_placeholder_or_mismatch",
        )
    )

    sig = host.manifest_signature.strip()
    sig_ok = (not is_unreviewed_placeholder(sig)) and not sig.upper().startswith("REQUIRED:")
    # Signatures must look like concrete hex (ed25519/sha256 style), not free text.
    if sig_ok and not (
        len(sig) >= 32 and all(c in "0123456789abcdefABCDEF" for c in sig.replace(":", ""))
    ):
        # Allow opaque reviewed tokens that are explicitly not placeholders and long enough.
        sig_ok = len(sig) >= 32 and " " not in sig
    checks.append(
        _check(
            "manifest_signature_concrete",
            sig_ok,
            "ok" if sig_ok else "signature_placeholder_or_missing",
        )
    )

    # Feature flags must remain false for plan-only Phase 9
    for flag, expected_false in (
        ("ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE", False),
        ("ENABLE_BRANCH_CACHE_ONE_NODE_STAGING_DEPLOY", False),
    ):
        actual = bool(host.feature_flags.get(flag, False))
        checks.append(
            _check(
                f"flag_{flag.lower()}_false",
                actual is expected_false,
                "ok" if actual is expected_false else "flag_enabled",
            )
        )

    checks.append(
        _check(
            "rollback_prereq_prior_digest",
            host.rollback_prior_digest_recorded,
            "ok" if host.rollback_prior_digest_recorded else "prior_digest_missing",
        )
    )
    checks.append(
        _check(
            "forensic_dir",
            host.forensic_dir_writable,
            "ok" if host.forensic_dir_writable else "forensic_dir_unwritable",
        )
    )

    remaining_inputs = [
        "approved_staging_hostname_or_ip",
        "server_login",
        "operator_ca_and_client_certificate_material",
        "secret_mounts",
        "dns_record",
        "cloudflare_or_r2_account",
        "real_credentials",
        "reviewed_egress_application",
        "concrete_sbom_provenance_and_manifest_signature",
    ]

    failed = [c for c in checks if not c.ok]
    go = not failed
    # plan_success requires every check green AND concrete reviewed evidence (no placeholders).
    plan_success = go and not placeholders and sig_ok
    return {
        "schema_version": "ifilm.branch_node.staging_preflight.v1",
        "mode": "plan_readonly",
        "mutates_host": False,
        "classification": "plan_go" if go else "plan_no_go",
        "go": go,
        "plan_success": plan_success,
        "live_pilot_ready": False,
        "client_redirect_active": False,
        "deployment_authorized": False,
        "apply_allowed": False,
        "checks": [c.as_dict() for c in checks],
        "failed": [c.name for c in failed],
        "placeholder_fields": placeholders,
        "remaining_live_deployment_inputs": remaining_inputs,
        "evidence_redaction": "secrets_and_identifiers_redacted",
        "inventory_node_id": inventory.node_id,
        "origin_host": inventory.origin.host,
        "origin_pinned_ip": inventory.origin.pinned_resolved_ipv4,
        "expected_client_identity": inventory.expected_client_identity,
        "image_digest": inventory.image.digest,
        "evaluated_at_utc": now.isoformat().replace("+00:00", "Z"),
    }


def with_host_overrides(host: HostFacts, **kwargs: Any) -> HostFacts:
    """Return a copy of HostFacts with selected fields replaced (tests/helpers)."""
    return replace(host, **kwargs)


def write_preflight_report(path: Path, report: dict[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
