"""Pilot readiness / simulation harness — no external systems."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.services.branch_cache import metrics
from app.services.branch_cache.data_plane.engine import BranchDataPlaneEngine, build_sim_engine
from app.services.branch_cache.grants import issue_edge_grant


@dataclass
class SimScenarioResult:
    name: str
    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)


def write_mini_package(origin_root: Path, *, asset_id: str, package_id: str) -> None:
    base = origin_root / asset_id / package_id
    (base / "720p").mkdir(parents=True, exist_ok=True)
    (base / "master.m3u8").write_text(
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\n720p/index.m3u8\n",
        encoding="utf-8",
    )
    (base / "720p" / "index.m3u8").write_text(
        "#EXTM3U\n#EXTINF:6.0,\nseg_000.ts\n#EXT-X-ENDLIST\n",
        encoding="utf-8",
    )
    (base / "720p" / "seg_000.ts").write_bytes(b"\x00\x01SEGDATA" * 1024)


def run_pilot_readiness_report(
    *,
    cache_root: Path,
    origin_root: Path,
    settings: Settings,
    public_key_pem: str,
    node_id: str = "pilot-node-01",
    site_id: str = "kabul",
) -> dict[str, Any]:
    """Model hit ratio, origin bytes, fill latency, eviction, outage fallback, capacity."""
    metrics.reset_for_tests()
    write_mini_package(origin_root, asset_id="asset-1", package_id="pkg-1")
    engine = build_sim_engine(
        cache_root=cache_root,
        origin_root=origin_root,
        node_id=node_id,
        site_id=site_id,
        public_key_pem=public_key_pem,
        settings=settings,
        high_watermark_bytes=50_000,
        low_watermark_bytes=20_000,
        min_free_bytes=5_000,
    )

    results: list[SimScenarioResult] = []
    path_prefix = "/hls/pkg-1/"

    def _grant(session: str = "sess-1") -> str:
        token, _ = issue_edge_grant(
            node_id=node_id,
            site_id=site_id,
            package_id="pkg-1",
            session_id=session,
            path_prefix=path_prefix,
            settings=settings,
        )
        return token

    # Cold miss fill
    t0 = time.perf_counter()
    r1 = engine.serve(
        grant_token=_grant("s1"),
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="s1",
        relative_path="720p/seg_000.ts",
        path_prefix=path_prefix,
        enforce_replay=True,
    )
    fill_ms = (time.perf_counter() - t0) * 1000
    results.append(
        SimScenarioResult(
            "cold_miss_fill",
            r1.status_code == 200 and r1.decision.decision == "cache_miss_filled",
            {"fill_latency_ms": round(fill_ms, 3), "bytes": r1.content_length},
        )
    )

    # Hit
    r2 = engine.serve(
        grant_token=_grant("s2"),
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="s2",
        relative_path="720p/seg_000.ts",
        path_prefix=path_prefix,
    )
    results.append(
        SimScenarioResult(
            "cache_hit",
            r2.status_code == 200 and r2.decision.from_cache,
            {"bytes": r2.content_length},
        )
    )

    # Range
    r3 = engine.serve(
        grant_token=_grant("s3"),
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="s3",
        relative_path="720p/seg_000.ts",
        path_prefix=path_prefix,
        range_header="bytes=0-15",
    )
    results.append(
        SimScenarioResult(
            "byte_range",
            r3.status_code == 206 and r3.content_length == 16,
            {"content_range": r3.content_range},
        )
    )

    # Manifest
    r4 = engine.serve(
        grant_token=_grant("s4"),
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="s4",
        relative_path="master.m3u8",
        path_prefix=path_prefix,
    )
    results.append(
        SimScenarioResult(
            "manifest",
            r4.status_code == 200 and "mpegurl" in r4.content_type,
            {"cache_control": r4.cache_control},
        )
    )

    # Auth failure (wrong node) — need token for other node
    bad_settings = settings
    try:
        from app.services.branch_cache.grants import issue_edge_grant as issue

        bad_token, _ = issue(
            node_id="other-node",
            site_id=site_id,
            package_id="pkg-1",
            session_id="s5",
            path_prefix=path_prefix,
            settings=bad_settings,
        )
        r5 = engine.serve(
            grant_token=bad_token,
            asset_id="asset-1",
            package_id="pkg-1",
            session_id="s5",
            relative_path="master.m3u8",
            path_prefix=path_prefix,
        )
        results.append(SimScenarioResult("auth_denied_wrong_node", r5.status_code == 403, {}))
    except Exception as exc:  # noqa: BLE001
        results.append(
            SimScenarioResult("auth_denied_wrong_node", False, {"error": type(exc).__name__})
        )

    # Origin outage fallback
    engine.origin.fail_paths = frozenset({"720p/index.m3u8"})  # type: ignore[attr-defined]
    r6 = engine.serve(
        grant_token=_grant("s6"),
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="s6",
        relative_path="720p/index.m3u8",
        path_prefix=path_prefix,
    )
    results.append(
        SimScenarioResult(
            "origin_outage_fallback",
            r6.decision.fallback_to_central and not engine.cache.has("720p/index.m3u8"),
            {"decision": r6.decision.decision},
        )
    )

    # Capacity / eviction: fill many small objects by writing extras into origin
    for i in range(20):
        name = f"720p/extra_{i:02d}.ts"
        (origin_root / "asset-1" / "pkg-1" / "720p" / f"extra_{i:02d}.ts").write_bytes(b"X" * 4000)
        engine.serve(
            grant_token=_grant(f"ev-{i}"),
            asset_id="asset-1",
            package_id="pkg-1",
            session_id=f"ev-{i}",
            relative_path=name,
            path_prefix=path_prefix,
        )
    cache_status = engine.cache.status()
    results.append(
        SimScenarioResult(
            "capacity_bounded",
            cache_status["used_bytes"] <= cache_status["high_watermark_bytes"],
            cache_status,
        )
    )

    snap = metrics.snapshot()
    hits = int(snap.get("dp_hit", 0))
    misses = int(snap.get("dp_miss", 0))
    hit_ratio = (hits / (hits + misses)) if (hits + misses) else 0.0
    origin_bytes = int(snap.get("dp_bytes_origin", 0))
    served_bytes = int(snap.get("dp_bytes_served", 0))
    saved = max(0, served_bytes - origin_bytes)  # hits save re-fetch; coarse model

    return {
        "pilot_ready": all(r.ok for r in results),
        "scenarios": [{"name": r.name, "ok": r.ok, "detail": r.detail} for r in results],
        "model": {
            "hit_ratio": round(hit_ratio, 4),
            "origin_bytes": origin_bytes,
            "served_bytes": served_bytes,
            "approx_bytes_saved_vs_all_miss": saved,
            "fill_latency_ms_sample": results[0].detail.get("fill_latency_ms"),
            "evictions_implied": snap.get("dp_evicted", 0),
            "fallbacks": snap.get("dp_fallback", 0),
            "auth_failures": snap.get("dp_auth_fail", 0),
        },
        "counters": snap,
        "cache": cache_status,
        "client_redirect_active": False,
        "data_plane_mode": "simulation",
        "live_network": False,
    }


def engine_status(engine: BranchDataPlaneEngine) -> dict[str, Any]:
    return {
        "enabled": engine.enabled(),
        "node_id": engine.node_id,
        "site_id": engine.site_id,
        "cache": engine.cache.status(),
        "prewarm": engine.prewarm.status(),
        "counters": metrics.snapshot(),
        "client_redirect_active": False,
        "live_http_origin_fetcher": False,
    }
