"""Offline workload/trace simulator over the Phase 4 data-plane engine."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.core.config import Settings
from app.services.branch_cache import metrics
from app.services.branch_cache.data_plane.engine import build_sim_engine
from app.services.branch_cache.data_plane.sim_harness import write_mini_package
from app.services.branch_cache.grants import clear_replay_cache_for_tests, issue_edge_grant

WorkloadPhase = Literal[
    "cold_start",
    "steady_state",
    "popular_skew",
    "seek_range",
    "eviction_churn",
    "node_drain",
    "origin_outage",
    "origin_timeout",
    "checksum_fail",
    "recovery",
]


@dataclass(frozen=True)
class TraceEvent:
    phase: WorkloadPhase
    relative_path: str
    session_id: str
    range_header: str | None = None
    expect_fallback: bool = False


@dataclass
class PhaseStats:
    requests: int = 0
    hits: int = 0
    misses: int = 0
    fallbacks: int = 0
    auth_fails: int = 0
    fill_latencies_ms: list[float] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        lat = sorted(self.fill_latencies_ms)
        p95 = lat[int(0.95 * (len(lat) - 1))] if lat else 0.0
        return {
            "requests": self.requests,
            "hits": self.hits,
            "misses": self.misses,
            "fallbacks": self.fallbacks,
            "auth_fails": self.auth_fails,
            "p95_fill_latency_ms": round(p95, 3),
        }


def _zipf_choice(n: int, rank: int, *, alpha: float = 1.1) -> int:
    """Deterministic Zipf-like index in [0, n)."""
    if n <= 0:
        return 0
    # Hash rank into weighted bucket without randomness.
    weights = [(i + 1) ** (-alpha) for i in range(n)]
    total = sum(weights)
    target = (hashlib.sha256(str(rank).encode()).digest()[0] / 255.0) * total
    acc = 0.0
    for i, w in enumerate(weights):
        acc += w
        if target <= acc:
            return i
    return n - 1


def build_deterministic_trace(
    *, title_count: int = 5, segments_per_title: int = 4
) -> list[TraceEvent]:
    """Build a fixed multi-phase offline workload (no customer data)."""
    events: list[TraceEvent] = []
    # Cold start: unique objects
    for t in range(title_count):
        events.append(TraceEvent("cold_start", f"t{t}/seg_000.ts", f"cold-{t}"))
    # Steady state: revisit first objects
    for i in range(title_count * 2):
        t = i % max(1, title_count // 2 or 1)
        events.append(TraceEvent("steady_state", f"t{t}/seg_000.ts", f"steady-{i}"))
    # Popular skew
    for i in range(20):
        t = _zipf_choice(title_count, i)
        seg = _zipf_choice(segments_per_title, i + 7)
        events.append(TraceEvent("popular_skew", f"t{t}/seg_{seg:03d}.ts", f"skew-{i}"))
    # Seek/range
    for i in range(8):
        events.append(
            TraceEvent(
                "seek_range",
                "t0/seg_000.ts",
                f"seek-{i}",
                range_header=f"bytes={i * 16}-{(i * 16) + 15}",
            )
        )
    # Eviction churn: many unique large-ish objects (created in fixture)
    for i in range(12):
        events.append(TraceEvent("eviction_churn", f"churn/extra_{i:02d}.ts", f"churn-{i}"))
    # Drain phase (engine.cache.draining toggled by runner)
    for i in range(3):
        events.append(
            TraceEvent("node_drain", f"t{i}/seg_001.ts", f"drain-{i}", expect_fallback=True)
        )
    # Origin failures
    events.append(TraceEvent("origin_outage", "fail/outage.ts", "outage-1", expect_fallback=True))
    events.append(
        TraceEvent("origin_timeout", "fail/timeout.ts", "timeout-1", expect_fallback=True)
    )
    events.append(TraceEvent("checksum_fail", "fail/badsum.ts", "badsum-1", expect_fallback=True))
    # Recovery after origin restored
    for i in range(4):
        events.append(TraceEvent("recovery", f"t{i}/seg_000.ts", f"rec-{i}"))
    return events


def prepare_workload_origin(origin_root: Path, *, title_count: int = 5, segments: int = 4) -> None:
    """Write synthetic package trees for the workload (lab only)."""
    for t in range(title_count):
        base = origin_root / "asset-1" / "pkg-1" / f"t{t}"
        base.mkdir(parents=True, exist_ok=True)
        for s in range(segments):
            (base / f"seg_{s:03d}.ts").write_bytes(bytes([t, s]) * 512)
        (base / "index.m3u8").write_text("#EXTM3U\n", encoding="utf-8")
    # Also mini package for harness compatibility
    write_mini_package(origin_root, asset_id="asset-1", package_id="pkg-1")
    churn = origin_root / "asset-1" / "pkg-1" / "churn"
    churn.mkdir(parents=True, exist_ok=True)
    for i in range(12):
        (churn / f"extra_{i:02d}.ts").write_bytes(b"C" * 3000)
    fail = origin_root / "asset-1" / "pkg-1" / "fail"
    fail.mkdir(parents=True, exist_ok=True)
    (fail / "outage.ts").write_bytes(b"O" * 100)
    (fail / "timeout.ts").write_bytes(b"T" * 100)
    (fail / "badsum.ts").write_bytes(b"B" * 100)


def run_workload_simulation(
    *,
    cache_root: Path,
    origin_root: Path,
    settings: Settings,
    public_key_pem: str,
    node_id: str = "lab-node-01",
    site_id: str = "kabul",
    high_watermark_bytes: int = 40_000,
    low_watermark_bytes: int = 15_000,
    min_free_bytes: int = 3_000,
) -> dict[str, Any]:
    """Execute deterministic offline workload; no network, no customer data."""
    metrics.reset_for_tests()
    clear_replay_cache_for_tests()
    prepare_workload_origin(origin_root)
    engine = build_sim_engine(
        cache_root=cache_root,
        origin_root=origin_root,
        node_id=node_id,
        site_id=site_id,
        public_key_pem=public_key_pem,
        settings=settings,
        high_watermark_bytes=high_watermark_bytes,
        low_watermark_bytes=low_watermark_bytes,
        min_free_bytes=min_free_bytes,
    )
    # Wire failure paths on LocalDirOriginFetcher
    engine.origin.fail_paths = frozenset({"fail/outage.ts"})  # type: ignore[attr-defined]
    engine.origin.timeout_paths = frozenset({"fail/timeout.ts"})  # type: ignore[attr-defined]
    engine.origin.corrupt_checksum_paths = frozenset({"fail/badsum.ts"})  # type: ignore[attr-defined]

    path_prefix = "/hls/pkg-1/"
    phases: dict[str, PhaseStats] = {}
    trace = build_deterministic_trace()

    for ev in trace:
        stats = phases.setdefault(ev.phase, PhaseStats())
        if ev.phase == "node_drain":
            engine.cache.draining = True
        elif ev.phase == "recovery":
            engine.cache.draining = False
            engine.origin.fail_paths = frozenset()  # type: ignore[attr-defined]
            engine.origin.timeout_paths = frozenset()  # type: ignore[attr-defined]
            engine.origin.corrupt_checksum_paths = frozenset()  # type: ignore[attr-defined]

        token, _ = issue_edge_grant(
            node_id=node_id,
            site_id=site_id,
            package_id="pkg-1",
            session_id=ev.session_id,
            path_prefix=path_prefix,
            settings=settings,
        )
        t0 = time.perf_counter()
        resp = engine.serve(
            grant_token=token,
            asset_id="asset-1",
            package_id="pkg-1",
            session_id=ev.session_id,
            relative_path=ev.relative_path,
            path_prefix=path_prefix,
            range_header=ev.range_header,
            enforce_replay=True,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        stats.requests += 1
        if resp.status_code == 403:
            stats.auth_fails += 1
        elif resp.decision.fallback_to_central:
            stats.fallbacks += 1
        elif resp.decision.from_cache:
            stats.hits += 1
        else:
            stats.misses += 1
            stats.fill_latencies_ms.append(elapsed_ms)

    snap = metrics.snapshot()
    total_req = sum(p.requests for p in phases.values())
    total_hits = sum(p.hits for p in phases.values())
    total_miss = sum(p.misses for p in phases.values())
    total_fb = sum(p.fallbacks for p in phases.values())
    total_auth = sum(p.auth_fails for p in phases.values())
    all_lat = [x for p in phases.values() for x in p.fill_latencies_ms]
    all_lat.sort()
    p95 = all_lat[int(0.95 * (len(all_lat) - 1))] if all_lat else 0.0
    denom = total_hits + total_miss
    hit_ratio = (total_hits / denom) if denom else 0.0
    origin_bytes = int(snap.get("dp_bytes_origin", 0))
    served_bytes = int(snap.get("dp_bytes_served", 0))

    return {
        "label": "lab_workload_simulation",
        "live_network": False,
        "customer_data": False,
        "client_redirect_active": False,
        "phases": {k: v.as_dict() for k, v in phases.items()},
        "totals": {
            "requests": total_req,
            "hits": total_hits,
            "misses": total_miss,
            "fallbacks": total_fb,
            "auth_fails": total_auth,
            "hit_ratio": round(hit_ratio, 4),
            "origin_bytes": origin_bytes,
            "served_bytes": served_bytes,
            "approx_bytes_saved": max(0, served_bytes - origin_bytes),
            "p95_fill_latency_ms": round(p95, 3),
            "evicted": int(snap.get("dp_evicted", 0)),
            "partial_files_remaining": engine.cache.cleanup_partials(),
        },
        "cache": engine.cache.status(),
        "counters": snap,
    }
