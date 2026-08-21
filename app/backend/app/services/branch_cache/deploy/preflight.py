"""Read-only preflight / plan for one-node staging (Phase 9).

Never modifies the host. Host facts are injected for offline/unit tests.
Fails closed when required deployment inputs are absent or incomplete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.branch_cache.deploy.inventory import StagingInventoryV1
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
    has_client_auth_eku: bool


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
    client_cert: CertMaterialFact | None = None
    client_key_mode_bits: int = 0o600
    client_key_exists: bool = False
    edge_grant_public_sha256: str = ""
    image_digest_present: bool = True
    sbom_ref_present: bool = True
    provenance_ref_present: bool = True
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
    checks.append(
        _check(
            "operator_approval_record",
            bool(inventory.operator_approval.record_id)
            and not inventory.operator_approval.record_id.startswith("REQUIRED"),
            "ok" if inventory.operator_approval.record_id else "missing_approval",
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

    # Certs — metadata only
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

    if host.client_cert is None:
        checks.append(_check("client_cert_material", False, "client_cert_facts_absent"))
    else:
        checks.append(
            _check(
                "client_cert_exists", host.client_cert.exists and not host.client_cert.is_symlink
            )
        )
        checks.append(
            _check(
                "client_cert_fingerprint",
                host.client_cert.sha256_hex == inventory.trust.mtls_client_cert_sha256,
                "ok"
                if host.client_cert.sha256_hex == inventory.trust.mtls_client_cert_sha256
                else "client_fp_mismatch",
            )
        )
        checks.append(
            _check(
                "client_cert_eku",
                host.client_cert.has_client_auth_eku,
                "ok" if host.client_cert.has_client_auth_eku else "missing_client_auth_eku",
            )
        )
        san_ok = inventory.origin.host in host.client_cert.san_dns or bool(host.client_cert.san_dns)
        # Client cert SAN need not match origin host; record presence only.
        checks.append(
            _check(
                "client_cert_san_present",
                bool(host.client_cert.san_dns),
                "ok" if san_ok else "san_empty",
            )
        )
        try:
            not_after = datetime.fromisoformat(
                host.client_cert.not_after_utc.replace("Z", "+00:00")
            )
            remaining = (not_after - now).days
            checks.append(
                _check(
                    "client_cert_expiry",
                    remaining >= 7,
                    "ok" if remaining >= 7 else "cert_expiring_soon",
                )
            )
        except ValueError:
            checks.append(_check("client_cert_expiry", False, "invalid_not_after"))

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
    checks.append(_check("sbom_ref", host.sbom_ref_present or bool(inventory.image.sbom_ref)))
    checks.append(
        _check(
            "provenance_ref", host.provenance_ref_present or bool(inventory.image.provenance_ref)
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

    # Incomplete live inputs — always report as remaining inputs (informational
    # blockers for any future apply, not for plan rendering itself).
    remaining_inputs = [
        "approved_staging_hostname_or_ip",
        "server_login",
        "operator_ca_and_client_certificate_material",
        "secret_mounts",
        "dns_record",
        "cloudflare_or_r2_account",
        "real_credentials",
        "reviewed_egress_application",
    ]

    failed = [c for c in checks if not c.ok]
    go = not failed
    return {
        "schema_version": "ifilm.branch_node.staging_preflight.v1",
        "mode": "plan_readonly",
        "mutates_host": False,
        "classification": "plan_go" if go else "plan_no_go",
        "go": go,
        "live_pilot_ready": False,
        "client_redirect_active": False,
        "deployment_authorized": False,
        "apply_allowed": False,
        "checks": [c.as_dict() for c in checks],
        "failed": [c.name for c in failed],
        "remaining_live_deployment_inputs": remaining_inputs,
        "evidence_redaction": "secrets_and_identifiers_redacted",
        "inventory_node_id": inventory.node_id,
        "origin_host": inventory.origin.host,
        "origin_pinned_ip": inventory.origin.pinned_resolved_ipv4,
        "image_digest": inventory.image.digest,
        "evaluated_at_utc": now.isoformat().replace("+00:00", "Z"),
    }


def write_preflight_report(path: Path, report: dict[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
