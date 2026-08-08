#!/usr/bin/env python3
"""Safe local latency smoke (sequential). Not a production load test of ifilm.af."""

from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET", "qa-jwt-secret-value-32chars-minxx")
os.environ.setdefault("ADMIN_BOOTSTRAP_PASSWORD", "qa-admin-pass-ok")
os.environ.setdefault("FRONTEND_DIST", "")
os.environ.setdefault("ENABLE_RADIUS_LOGIN", "true")
os.environ.setdefault("RADIUS_MODE", "mock")
os.environ.setdefault("RADIUS_ENABLED", "true")
os.environ.setdefault("RADIUS_SECRET", "qa")
os.environ.setdefault(
    "RADIUS_MOCK_USERS",
    json.dumps(
        [
            {
                "username": "mobin_user_001",
                "password": "fixture-pass-ok",
                "package": "Premium",
                "branch": "Kabul",
                "expiration": "2026-12-31",
                "name": "Ahmad",
            }
        ]
    ),
)

from app.core.config import get_settings

get_settings.cache_clear()

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.bootstrap import seed_development_data
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.content import Movie
from app.services.catalog import utcnow


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, int(round(p * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def main() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    seed_development_data(db, include_demo_catalog=True)
    now = utcnow()
    for i in range(40):
        db.add(
            Movie(
                title=f"Load {i}",
                original_title=f"Load {i}",
                slug=f"load-{i}",
                description="d",
                short_description="s",
                release_year=2020,
                duration_minutes=100,
                status="published",
                published_at=now,
                views=100 - i,
                is_featured=i < 4,
            )
        )
    db.commit()
    db.close()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    login = client.post(
        "/api/auth/subscriber/login",
        json={"username": "mobin_user_001", "password": "fixture-pass-ok"},
    )
    token = login.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    scenarios = [
        ("anon_home", "/api/catalog/home?locale=en", None),
        ("auth_home", "/api/me/home?locale=en", auth),
        ("movies", "/api/movies?page_size=20&sort=newest", None),
        ("movie_detail", "/api/movies/load-0", None),
    ]

    report: dict = {
        "label": "local-latency-smoke",
        "note": "Sequential TestClient timings (SQLite). Not concurrent prod load.",
        "iterations": 50,
        "scenarios": {},
    }
    for name, path, headers in scenarios:
        latencies: list[float] = []
        errors = 0
        t0 = time.perf_counter()
        for _ in range(50):
            start = time.perf_counter()
            resp = client.get(path, headers=headers or {})
            latencies.append((time.perf_counter() - start) * 1000)
            if resp.status_code >= 400:
                errors += 1
        wall = time.perf_counter() - t0
        latencies.sort()
        report["scenarios"][name] = {
            "requests": len(latencies),
            "rps": round(len(latencies) / wall, 1) if wall else 0,
            "median_ms": round(statistics.median(latencies), 1),
            "p95_ms": round(_pct(latencies, 0.95), 1),
            "errors": errors,
        }

    out = Path("/opt/cursor/artifacts/perf-customer-browsing-v1/load-smoke.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
