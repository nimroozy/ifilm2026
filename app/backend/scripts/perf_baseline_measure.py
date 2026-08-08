#!/usr/bin/env python3
"""Measure customer browsing API query counts / latency (synthetic published catalog).

Usage (from app/backend):
  PYTHONPATH=. python scripts/perf_baseline_measure.py
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
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
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.bootstrap import seed_development_data
from app.db import session as session_module
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.content import Genre, Movie, Series
from app.models.content_translations import ContentTranslation
from app.models.credits import MovieCastCredit
from app.models.user import Subscriber, WatchlistItem
from app.services.catalog import utcnow
from app.utils.slug import normalize_slug


def _build_catalog(db) -> None:
    seed_development_data(db, include_demo_catalog=True)
    genre_names = ["Action", "Comedy", "Drama", "Family", "Thriller", "Adventure"]
    genres: dict[str, Genre] = {}
    for name in genre_names:
        g = db.query(Genre).filter(Genre.name == name).one_or_none()
        if g is None:
            g = Genre(name=name, slug=normalize_slug(name))
            db.add(g)
            db.flush()
        genres[name] = g

    now = utcnow()
    movies: list[Movie] = []
    for i in range(80):
        g1 = genre_names[i % len(genre_names)]
        g2 = genre_names[(i + 1) % len(genre_names)]
        m = Movie(
            title=f"Perf Movie {i:02d}",
            slug=f"perf-movie-{i:02d}",
            description=f"Description for movie {i} " * 8,
            short_description=f"Short {i}",
            release_year=1990 + (i % 35),
            duration_minutes=90 + (i % 60),
            language="English" if i % 3 else "Dari",
            country="USA" if i % 2 else "Afghanistan",
            imdb_rating=5.0 + (i % 50) / 10,
            views=1000 + i * 137,
            poster_url=f"https://placehold.co/300x450/111/eee?text=M{i}",
            backdrop_url=f"https://placehold.co/1920x800/111/eee?text=B{i}",
            status="published",
            published_at=now,
            is_featured=(i < 8),
            is_trending=(8 <= i < 20),
            cast=[f"Actor {i}", f"Actor {i + 1}"],
            dubbed=["Persian"] if i % 4 == 0 else [],
            subtitles=["English", "Dari"],
            audio=["English"],
            created_at=now,
            updated_at=now,
        )
        m.genre_links = [genres[g1], genres[g2]]
        db.add(m)
        db.flush()
        movies.append(m)
        for locale, title in (("en", m.title), ("fa", f"فیلم {i}")):
            db.add(
                ContentTranslation(
                    entity_type="movie",
                    entity_id=m.id,
                    locale=locale,
                    field_key="title",
                    value=title,
                    source="manual",
                )
            )
            db.add(
                ContentTranslation(
                    entity_type="movie",
                    entity_id=m.id,
                    locale=locale,
                    field_key="description",
                    value=m.description,
                    source="manual",
                )
            )
        for order, name in enumerate([f"Star {i}", f"Co-star {i}"]):
            db.add(
                MovieCastCredit(
                    movie_id=m.id,
                    tmdb_person_id=1000 + i * 10 + order,
                    name=name,
                    character_name=f"Role {order}",
                    credit_order=order,
                )
            )

    for i in range(20):
        s = Series(
            title=f"Perf Series {i:02d}",
            slug=f"perf-series-{i:02d}",
            description=f"Series description {i}",
            short_description=f"S{i}",
            release_year=2010 + i,
            language="English",
            country="USA",
            imdb_rating=7.0,
            views=5000 + i * 200,
            poster_url=f"https://placehold.co/300x450/222/eee?text=S{i}",
            backdrop_url=f"https://placehold.co/1920x800/222/eee?text=SB{i}",
            status="published",
            published_at=now,
            created_at=now,
            updated_at=now,
        )
        s.genre_links = [genres["Drama"], genres["Action"]]
        db.add(s)

    user = db.query(Subscriber).filter(Subscriber.username == "mobin_user_001").one()
    for m in movies[:5]:
        db.add(WatchlistItem(subscriber_id=user.id, movie_id=m.id, created_at=now))
    db.commit()


def main() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session_module.reset_engine_for_tests(engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        _build_catalog(db)
    finally:
        db.close()

    app = create_app()

    def _override_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)

    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        statements.append(statement)

    def classify(stmts: list[str]) -> dict[str, int]:
        kinds: Counter[str] = Counter()
        for s in stmts:
            s_norm = " ".join(s.split()).lower()
            if not s_norm.startswith("select"):
                kinds["non_select"] += 1
                continue
            matched = False
            for table in [
                "movies",
                "series",
                "genres",
                "movie_genres",
                "series_genres",
                "content_translations",
                "media_assets",
                "media_packages",
                "movie_cast_credits",
                "series_cast_credits",
                "collections",
                "collection_items",
                "user_watch_progress",
                "watchlist_items",
                "subscribers",
                "seasons",
                "episodes",
            ]:
                if table in s_norm:
                    kinds[table] += 1
                    matched = True
                    break
            if not matched:
                kinds["other_select"] += 1
        return dict(kinds.most_common())

    def measure(label: str, path: str, headers: dict | None = None) -> dict:
        statements.clear()
        t0 = time.perf_counter()
        resp = client.get(path, headers=headers or {})
        ms = (time.perf_counter() - t0) * 1000
        return {
            "label": label,
            "path": path,
            "status": resp.status_code,
            "latency_ms": round(ms, 1),
            "bytes": len(resp.content),
            "query_count": len(statements),
            "by_table": classify(statements),
        }

    login = client.post(
        "/api/auth/subscriber/login",
        json={"username": "mobin_user_001", "password": "fixture-pass-ok"},
    )
    assert login.status_code == 200, login.text
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
    client.get("/api/health")

    results = []
    for label, path in [
        ("movies_featured", "/api/movies?featured=true&page_size=8&sort=newest&locale=en"),
        ("movies_trending", "/api/movies?trending=true&page_size=12&sort=views_desc&locale=en"),
        ("movies_newest", "/api/movies?page_size=12&sort=newest&locale=en"),
        ("movies_top_rated", "/api/movies?page_size=12&sort=rating_desc&locale=en"),
        ("movies_pool40", "/api/movies?page_size=40&sort=newest&locale=en"),
        ("series_popular", "/api/series?page_size=12&sort=views_desc&locale=en"),
        ("movies_action", "/api/movies?genre=Action&page_size=12&sort=views_desc&locale=en"),
        ("movies_comedy", "/api/movies?genre=Comedy&page_size=12&sort=views_desc&locale=en"),
        ("collections_featured", "/api/catalog/collections/featured/home?page_size=6"),
        ("recs_home_anon", "/api/recommendations/home"),
        ("browse_movies100", "/api/movies?page_size=100&sort=newest&locale=en"),
        ("browse_series100", "/api/series?page_size=100&sort=views_desc&locale=en"),
        ("genres", "/api/genres?page_size=50"),
    ]:
        results.append(measure(label, path))

    results.append(measure("continue_watching", "/api/me/continue-watching", auth))
    results.append(measure("watchlist", "/api/me/watchlist?page=1&page_size=20", auth))
    results.append(measure("recs_home_auth", "/api/me/recommendations/home", auth))
    slug = client.get("/api/movies?page_size=1&sort=newest").json()["data"][0]["slug"]
    results.append(measure("movie_detail", f"/api/movies/{slug}?locale=en"))

    # Optional new aggregated home endpoints (present after optimization)
    for label, path, headers in [
        ("catalog_home_anon", "/api/catalog/home?locale=en", None),
        ("me_home_auth", "/api/me/home?locale=en", auth),
    ]:
        statements.clear()
        t0 = time.perf_counter()
        resp = client.get(path, headers=headers or {})
        ms = (time.perf_counter() - t0) * 1000
        if resp.status_code == 404:
            continue
        results.append(
            {
                "label": label,
                "path": path,
                "status": resp.status_code,
                "latency_ms": round(ms, 1),
                "bytes": len(resp.content),
                "query_count": len(statements),
                "by_table": classify(statements),
            }
        )

    wave_a_labels = {
        "movies_featured",
        "movies_trending",
        "movies_newest",
        "movies_top_rated",
        "movies_pool40",
        "series_popular",
        "movies_action",
        "movies_comedy",
        "collections_featured",
    }
    wave_a = [r for r in results if r["label"] in wave_a_labels]
    auth_extra = [r for r in results if r["label"] in {"continue_watching", "watchlist", "recs_home_auth"}]
    anon_extra = [r for r in results if r["label"] == "recs_home_anon"]
    catalog_home = next((r for r in results if r["label"] == "catalog_home_anon"), None)
    me_home = next((r for r in results if r["label"] == "me_home_auth"), None)

    summary = {
        "label": os.environ.get("PERF_MEASURE_LABEL", "baseline"),
        "catalog": "synthetic 80 published movies / 20 published series + translations + cast",
        "simulated_anon_home_fanout": {
            "api_calls": len(wave_a) + len(anon_extra),
            "total_queries": sum(r["query_count"] for r in wave_a + anon_extra),
            "sum_latency_ms": round(sum(r["latency_ms"] for r in wave_a + anon_extra), 1),
            "total_bytes": sum(r["bytes"] for r in wave_a + anon_extra),
        },
        "simulated_auth_home_fanout": {
            "api_calls": len(wave_a) + len(auth_extra),
            "total_queries": sum(r["query_count"] for r in wave_a + auth_extra),
            "sum_latency_ms": round(sum(r["latency_ms"] for r in wave_a + auth_extra), 1),
            "total_bytes": sum(r["bytes"] for r in wave_a + auth_extra),
        },
        "aggregated_home": {
            "catalog_home_anon": catalog_home,
            "me_home_auth": me_home,
        },
        "endpoints": results,
    }

    out_dir = Path(os.environ.get("PERF_ARTIFACT_DIR", "/opt/cursor/artifacts/perf-customer-browsing-v1"))
    out_dir.mkdir(parents=True, exist_ok=True)
    name = os.environ.get("PERF_MEASURE_OUT", "baseline-api.json")
    (out_dir / name).write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in summary if k != "endpoints"}, indent=2))
    print("--- endpoints by query count ---")
    for r in sorted(results, key=lambda x: -x["query_count"]):
        print(
            f"{r['query_count']:4d}q {r['latency_ms']:7.1f}ms {r['bytes']:8d}B "
            f"{r['label']:22s} {r['by_table']}"
        )


if __name__ == "__main__":
    main()
