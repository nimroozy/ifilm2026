"""Machine-readable pilot gate report (lab-ready / pilot-candidate only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GateThresholds:
    max_auth_fail_rate: float = 0.02
    max_fallback_rate: float = 0.35
    min_hit_ratio: float = 0.25
    min_origin_bytes_saved_ratio: float = 0.0  # optional; 0 means don't require savings
    max_p95_fill_latency_ms: float = 2000.0
    max_eviction_per_request: float = 2.0
    min_disk_headroom_ratio: float = 0.05
    max_partial_files: int = 0
    max_error_budget_burn: float = 0.40  # fallbacks+auth / requests
    require_central_playback_preserved: bool = True


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    actual: float | int | bool | str
    threshold: float | int | bool | str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "actual": self.actual,
            "threshold": self.threshold,
            "reason": self.reason,
        }


def evaluate_pilot_gates(
    *,
    workload: dict[str, Any],
    capacity: dict[str, Any] | None = None,
    central_playback_preserved: bool = True,
    thresholds: GateThresholds | None = None,
) -> dict[str, Any]:
    """Evaluate SLO-style gates. Never claims live pilot ready from synthetic data alone."""
    th = thresholds or GateThresholds()
    totals = workload.get("totals") or {}
    cache = workload.get("cache") or {}
    requests = max(1, int(totals.get("requests") or 0))
    auth_fails = int(totals.get("auth_fails") or 0)
    fallbacks = int(totals.get("fallbacks") or 0)
    hit_ratio = float(totals.get("hit_ratio") or 0.0)
    origin_bytes = int(totals.get("origin_bytes") or 0)
    served_bytes = int(totals.get("served_bytes") or 0)
    saved = int(totals.get("approx_bytes_saved") or max(0, served_bytes - origin_bytes))
    saved_ratio = (saved / served_bytes) if served_bytes > 0 else 0.0
    p95 = float(totals.get("p95_fill_latency_ms") or 0.0)
    evicted = int(totals.get("evicted") or 0)
    partials = int(totals.get("partial_files_remaining") or 0)
    used = int(cache.get("used_bytes") or 0)
    high = int(cache.get("high_watermark_bytes") or 1)
    headroom_ratio = max(0.0, (high - used) / high) if high else 0.0
    error_burn = (auth_fails + fallbacks) / requests

    results: list[GateResult] = []

    def add(
        name: str,
        passed: bool,
        actual: float | int | bool | str,
        threshold: float | int | bool | str,
        reason: str,
    ) -> None:
        results.append(GateResult(name, passed, actual, threshold, reason))

    auth_rate = auth_fails / requests
    add(
        "auth_fail_rate",
        auth_rate <= th.max_auth_fail_rate,
        round(auth_rate, 4),
        th.max_auth_fail_rate,
        "ok" if auth_rate <= th.max_auth_fail_rate else "auth_fail_rate_exceeded",
    )
    fb_rate = fallbacks / requests
    add(
        "fallback_rate",
        fb_rate <= th.max_fallback_rate,
        round(fb_rate, 4),
        th.max_fallback_rate,
        "ok" if fb_rate <= th.max_fallback_rate else "fallback_rate_exceeded",
    )
    add(
        "cache_hit_ratio",
        hit_ratio >= th.min_hit_ratio,
        round(hit_ratio, 4),
        th.min_hit_ratio,
        "ok" if hit_ratio >= th.min_hit_ratio else "hit_ratio_below_threshold",
    )
    add(
        "origin_bytes_saved_ratio",
        saved_ratio >= th.min_origin_bytes_saved_ratio,
        round(saved_ratio, 4),
        th.min_origin_bytes_saved_ratio,
        "ok" if saved_ratio >= th.min_origin_bytes_saved_ratio else "insufficient_bytes_saved",
    )
    add(
        "p95_fill_latency_ms",
        p95 <= th.max_p95_fill_latency_ms,
        round(p95, 3),
        th.max_p95_fill_latency_ms,
        "ok" if p95 <= th.max_p95_fill_latency_ms else "p95_fill_latency_exceeded",
    )
    evict_rate = evicted / requests
    add(
        "eviction_churn",
        evict_rate <= th.max_eviction_per_request,
        round(evict_rate, 4),
        th.max_eviction_per_request,
        "ok" if evict_rate <= th.max_eviction_per_request else "eviction_churn_high",
    )
    add(
        "disk_headroom",
        headroom_ratio >= th.min_disk_headroom_ratio,
        round(headroom_ratio, 4),
        th.min_disk_headroom_ratio,
        "ok" if headroom_ratio >= th.min_disk_headroom_ratio else "disk_headroom_low",
    )
    add(
        "partial_files",
        partials <= th.max_partial_files,
        partials,
        th.max_partial_files,
        "ok" if partials <= th.max_partial_files else "partial_files_present",
    )
    add(
        "error_budget",
        error_burn <= th.max_error_budget_burn,
        round(error_burn, 4),
        th.max_error_budget_burn,
        "ok" if error_burn <= th.max_error_budget_burn else "error_budget_burned",
    )
    add(
        "central_playback_preserved",
        (not th.require_central_playback_preserved) or central_playback_preserved,
        central_playback_preserved,
        True,
        "ok" if central_playback_preserved else "central_playback_changed",
    )

    capacity_safe = True
    if capacity is not None:
        capacity_safe = bool(capacity.get("safe", False))
        add(
            "capacity_plan_safe",
            capacity_safe,
            capacity_safe,
            True,
            "ok" if capacity_safe else "capacity_plan_rejected",
        )

    all_passed = all(r.passed for r in results)
    # Synthetic-only: lab_ready if gates pass; pilot_candidate needs human+staging later.
    classification = "lab_ready" if all_passed else "lab_not_ready"
    return {
        "classification": classification,
        "lab_gates_passed": all_passed,
        "live_pilot_ready": False,  # NEVER true from synthetic-only evidence
        "requires_human_approval": True,
        "requires_staging_evidence": True,
        "client_redirect_active": False,
        "live_network": False,
        "gates": [r.as_dict() for r in results],
        "summary": {
            "requests": requests,
            "hit_ratio": round(hit_ratio, 4),
            "fallback_rate": round(fb_rate, 4),
            "auth_fail_rate": round(auth_rate, 4),
            "p95_fill_latency_ms": round(p95, 3),
            "approx_bytes_saved": saved,
            "disk_headroom_ratio": round(headroom_ratio, 4),
        },
        "pass_fail_reasons": [r.reason for r in results if not r.passed] or ["all_gates_passed"],
    }
