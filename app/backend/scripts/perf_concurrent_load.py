#!/usr/bin/env python3
"""Concurrent load smoke against local production-like stack (not ifilm.af)."""

from __future__ import annotations

import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

BASE = os.environ.get("PERF_BASE_URL", "http://127.0.0.1:8010")
OUT = Path(os.environ.get("PERF_ARTIFACT_DIR", "/opt/cursor/artifacts/perf-customer-browsing-v1"))
USER = os.environ.get("PERF_USER", "mobin_user_001")
PASS = os.environ.get("PERF_PASS", "fixture-pass-ok")


def _pct(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))]


def run_scenario(name: str, path: str, headers: dict | None, concurrencies: list[int], requests_per_worker: int = 4) -> dict:
    out: dict = {}
    for conc in concurrencies:
        latencies: list[float] = []
        errors = 0
        total = conc * requests_per_worker
        t0 = time.perf_counter()

        def one() -> tuple[int, float]:
            start = time.perf_counter()
            with httpx.Client(base_url=BASE, timeout=30.0) as client:
                resp = client.get(path, headers=headers or {})
            return resp.status_code, (time.perf_counter() - start) * 1000

        with ThreadPoolExecutor(max_workers=conc) as pool:
            futs = [pool.submit(one) for _ in range(total)]
            for fut in as_completed(futs):
                status, ms = fut.result()
                latencies.append(ms)
                if status >= 400:
                    errors += 1
        wall = time.perf_counter() - t0
        out[str(conc)] = {
            "requests": len(latencies),
            "rps": round(len(latencies) / wall, 1) if wall else 0,
            "p50_ms": round(statistics.median(latencies), 1) if latencies else 0,
            "p95_ms": round(_pct(latencies, 0.95), 1),
            "errors": errors,
        }
    return {name: out}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        login = client.post(
            "/api/auth/subscriber/login",
            json={"username": USER, "password": PASS},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    report = {
        "base": BASE,
        "note": "Local concurrent httpx against SQLite/WAL stack — not production.",
        "scenarios": {},
    }
    report["scenarios"].update(
        run_scenario("anonymous_homepage", "/api/catalog/home?locale=en", None, [10, 25, 50])
    )
    report["scenarios"].update(
        run_scenario("authenticated_homepage", "/api/me/home?locale=en", auth, [10, 25])
    )
    (OUT / "concurrent-load.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
