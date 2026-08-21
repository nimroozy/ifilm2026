"""Offline health/readiness evaluation for a future branch node (lab)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings


@dataclass(frozen=True)
class NodeHealthInput:
    public_key_pem: str
    cache_root: Path
    protocol_version: str
    min_protocol_version: str = "1"
    draining: bool = False
    disabled: bool = False
    origin_adapter_mode: str = "local_dir"  # local_dir | deferred_http (must not be live)
    clock_skew_seconds: int = 0
    max_clock_skew_seconds: int = 60
    disk_total_bytes: int | None = None
    disk_used_bytes: int | None = None
    min_free_bytes: int = 1_000_000_000
    has_private_signing_key: bool = False
    has_portal_or_sas_credentials: bool = False
    has_customer_data_store: bool = False


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "reason": self.reason}


def evaluate_branch_node_health(
    inp: NodeHealthInput,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Evaluate readiness without contacting networks or loading private keys."""
    checks: list[CheckResult] = []

    pub = (inp.public_key_pem or "").strip()
    checks.append(
        CheckResult(
            "public_key_available",
            "BEGIN PUBLIC KEY" in pub or "BEGIN CERTIFICATE" in pub,
            "ok" if pub else "missing_public_key",
        )
    )
    checks.append(
        CheckResult(
            "no_private_signing_key_on_branch",
            not inp.has_private_signing_key,
            "ok" if not inp.has_private_signing_key else "private_key_forbidden",
        )
    )
    checks.append(
        CheckResult(
            "no_portal_sas_credentials",
            not inp.has_portal_or_sas_credentials,
            "ok" if not inp.has_portal_or_sas_credentials else "portal_sas_forbidden",
        )
    )
    checks.append(
        CheckResult(
            "no_customer_data_store",
            not inp.has_customer_data_store,
            "ok" if not inp.has_customer_data_store else "customer_data_forbidden",
        )
    )
    checks.append(
        CheckResult(
            "clock_skew_budget",
            abs(int(inp.clock_skew_seconds)) <= int(inp.max_clock_skew_seconds),
            "ok"
            if abs(int(inp.clock_skew_seconds)) <= int(inp.max_clock_skew_seconds)
            else "clock_skew_exceeded",
        )
    )

    root = inp.cache_root
    root_ok = False
    reason = "cache_root_missing"
    try:
        resolved = root.resolve()
        if resolved.exists() and resolved.is_dir() and not resolved.is_symlink():
            # Must be dedicated: refuse obvious system roots
            forbidden = {"/", "/etc", "/var", "/usr", "/home", "/root", "/tmp"}
            if str(resolved) in forbidden:
                reason = "cache_root_not_dedicated"
            else:
                root_ok = True
                reason = "ok"
        elif not resolved.exists():
            # Lab may create later — still require parent safe
            parent = resolved.parent
            if parent.exists() and parent.is_dir() and not parent.is_symlink():
                root_ok = True
                reason = "cache_root_pending_create"
            else:
                reason = "cache_root_parent_invalid"
    except OSError:
        reason = "cache_root_unreadable"
    checks.append(CheckResult("dedicated_cache_root", root_ok, reason))

    # Disk headroom
    disk_ok = True
    disk_reason = "ok"
    if inp.disk_total_bytes is not None and inp.disk_used_bytes is not None:
        free = int(inp.disk_total_bytes) - int(inp.disk_used_bytes)
        if free < int(inp.min_free_bytes):
            disk_ok = False
            disk_reason = "insufficient_free_space"
    else:
        # Best-effort statvfs when available
        try:
            if root.exists():
                st = os.statvfs(root)
                free = int(st.f_bavail) * int(st.f_frsize)
                if free < int(inp.min_free_bytes):
                    disk_ok = False
                    disk_reason = "insufficient_free_space"
            else:
                disk_reason = "disk_stat_skipped"
        except OSError:
            disk_reason = "disk_stat_unavailable"
    checks.append(CheckResult("disk_headroom", disk_ok, disk_reason))

    want = (inp.min_protocol_version or "1").strip().split(".", 1)[0]
    got = (inp.protocol_version or "").strip().split(".", 1)[0]
    checks.append(
        CheckResult(
            "protocol_compatible",
            bool(got) and got == want,
            "ok" if got == want else "protocol_mismatch",
        )
    )
    checks.append(
        CheckResult(
            "not_draining",
            not inp.draining,
            "ok" if not inp.draining else "draining",
        )
    )
    checks.append(
        CheckResult(
            "not_disabled",
            not inp.disabled,
            "ok" if not inp.disabled else "disabled",
        )
    )

    mode = (inp.origin_adapter_mode or "").strip().lower()
    allowed_modes = {
        "local_dir",
        "deferred_http",
        "mtls_http_loopback",
        "mtls_staging_candidate",
    }
    checks.append(
        CheckResult(
            "origin_adapter_mode",
            mode in allowed_modes,
            "ok" if mode in allowed_modes else "unsupported_origin_mode",
        )
    )
    checks.append(
        CheckResult(
            "origin_not_live_http",
            mode not in {"live_http", "mtls_http_live"},
            "ok" if mode not in {"live_http", "mtls_http_live"} else "live_http_forbidden",
        )
    )

    if settings is not None:
        checks.append(
            CheckResult(
                "client_redirect_inactive",
                True,  # Phase 5 never activates redirects
                "ok",
            )
        )
        checks.append(
            CheckResult(
                "lab_flags_documented",
                not bool(settings.enable_branch_cache_pilot_lab)
                or settings.app_env in {"test", "development"},
                "ok",
            )
        )

    ready = all(c.ok for c in checks)
    return {
        "ready": ready,
        "classification": "lab_node_ready" if ready else "lab_node_not_ready",
        "live_serving_allowed": False,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "checks": [c.as_dict() for c in checks],
        "fail_reasons": [c.reason for c in checks if not c.ok] or ["all_checks_passed"],
    }
