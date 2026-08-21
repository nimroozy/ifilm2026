"""Staging-candidate readiness gates (offline / evidence-oriented).

Does not authorize live pilot or client redirects. Human approval required
before any separate deployment step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.services.branch_cache.enrollment.manifest import BranchNodeEnrollmentManifest
from app.services.branch_cache.ops.node_health import CheckResult


@dataclass(frozen=True)
class StagingGateInput:
    manifest: BranchNodeEnrollmentManifest
    cache_root: Path
    public_key_pem: str
    client_cert_not_after: datetime | None = None
    ca_bundle_path: Path | None = None
    client_cert_path: Path | None = None
    client_key_path: Path | None = None
    mtls_preflight_ok: bool = False
    mtls_preflight_reason: str = "not_run"
    disk_free_bytes: int | None = None
    clock_skew_seconds: int = 0
    human_approval_recorded: bool = False
    canary_shadow_only: bool = True
    min_cert_validity_days: int = 7


def evaluate_staging_candidate_gates(inp: StagingGateInput) -> dict[str, Any]:
    checks: list[CheckResult] = []

    checks.append(
        CheckResult(
            "live_pilot_ready_false",
            inp.manifest.live_pilot_ready is False,
            "ok",
        )
    )
    checks.append(
        CheckResult(
            "client_redirect_active_false",
            inp.manifest.client_redirect_active is False,
            "ok",
        )
    )
    checks.append(
        CheckResult(
            "canary_shadow_only",
            bool(inp.canary_shadow_only),
            "ok" if inp.canary_shadow_only else "canary_not_shadow_only",
        )
    )
    checks.append(
        CheckResult(
            "human_approval",
            bool(inp.human_approval_recorded),
            "ok" if inp.human_approval_recorded else "human_approval_required",
        )
    )
    checks.append(
        CheckResult(
            "environment_is_staging_candidate_or_lab",
            inp.manifest.environment in {"lab", "development", "staging-candidate", "test"},
            "ok",
        )
    )
    checks.append(
        CheckResult(
            "exactly_one_origin",
            len(inp.manifest.origin_allowlist) == 1,
            "ok",
        )
    )
    pub_ok = "BEGIN PUBLIC KEY" in (inp.public_key_pem or "") or "BEGIN CERTIFICATE" in (
        inp.public_key_pem or ""
    )
    checks.append(CheckResult("edge_grant_public_key", pub_ok, "ok" if pub_ok else "missing"))

    if inp.client_cert_not_after is not None:
        remaining = inp.client_cert_not_after - datetime.now(tz=UTC)
        ok = remaining >= timedelta(days=int(inp.min_cert_validity_days))
        checks.append(
            CheckResult(
                "client_cert_expiry_window",
                ok,
                "ok" if ok else "cert_expiring_soon",
            )
        )

    for label, path in (
        ("ca_bundle_mounted", inp.ca_bundle_path),
        ("client_cert_mounted", inp.client_cert_path),
        ("client_key_mounted", inp.client_key_path),
    ):
        if path is None:
            checks.append(CheckResult(label, False, "path_not_provided"))
        else:
            ok = path.is_file() and not path.is_symlink()
            checks.append(CheckResult(label, ok, "ok" if ok else "missing"))

    checks.append(
        CheckResult(
            "mtls_preflight",
            bool(inp.mtls_preflight_ok),
            inp.mtls_preflight_reason if not inp.mtls_preflight_ok else "ok",
        )
    )

    if inp.disk_free_bytes is not None:
        min_free = int(inp.manifest.resource_limits.min_free_bytes)
        ok = int(inp.disk_free_bytes) >= min_free
        checks.append(CheckResult("disk_capacity", ok, "ok" if ok else "insufficient_free_bytes"))

    checks.append(
        CheckResult(
            "clock_skew",
            abs(int(inp.clock_skew_seconds)) <= 60,
            "ok" if abs(int(inp.clock_skew_seconds)) <= 60 else "clock_skew",
        )
    )

    # Cache root dedicated
    root = inp.cache_root
    root_ok = False
    try:
        resolved = root.resolve()
        forbidden = {"/", "/etc", "/var", "/usr", "/home", "/root", "/tmp"}
        root_ok = str(resolved) not in forbidden
    except OSError:
        root_ok = False
    checks.append(CheckResult("dedicated_cache_root", root_ok, "ok" if root_ok else "bad_root"))

    failed = [c for c in checks if not c.ok]
    classification = "staging_candidate_ready" if not failed else "not_ready"
    # Never flip live pilot from this gate.
    return {
        "classification": classification,
        "ready": not failed,
        "live_pilot_ready": False,
        "client_redirect_active": False,
        "checks": [c.as_dict() for c in checks],
        "failed": [c.name for c in failed],
        "evidence_redaction": "secrets_redacted",
        "deployment_authorized": False,
        "note": (
            "Passing gates prepares a staging package only; "
            "live activation requires a separate explicit deployment step."
        ),
    }
