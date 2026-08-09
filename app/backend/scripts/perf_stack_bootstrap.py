#!/usr/bin/env python3
"""Bootstrap a file-SQLite catalog for local production-like perf QA."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path("/tmp/ifilm-perf-stack")
ROOT.mkdir(parents=True, exist_ok=True)
DB = ROOT / "catalog.db"
MEDIA = ROOT / "media"
ARTWORK = ROOT / "artwork"
for p in (MEDIA, ARTWORK):
    p.mkdir(parents=True, exist_ok=True)
for cat in ("originals", "trailers", "subtitles", "audio", "posters", "backdrops", "temp", "packages"):
    (MEDIA / cat).mkdir(parents=True, exist_ok=True)

os.environ["APP_ENV"] = "development"
os.environ["DEBUG"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["JWT_SECRET"] = "perf-stack-jwt-secret-value-32chars-min"
os.environ["ADMIN_BOOTSTRAP_PASSWORD"] = "perf-admin-pass-ok"
os.environ["ADMIN_BOOTSTRAP_USERNAME"] = "admin"
os.environ["ADMIN_BOOTSTRAP_EMAIL"] = "admin@perf.test"
os.environ["FRONTEND_DIST"] = str(Path("/workspace/app/frontend/dist").resolve())
os.environ["ENABLE_RADIUS_LOGIN"] = "true"
os.environ["RADIUS_MODE"] = "mock"
os.environ["RADIUS_ENABLED"] = "true"
os.environ["RADIUS_SECRET"] = "perf"
os.environ["MEDIA_ROOT"] = str(MEDIA)
os.environ["ARTWORK_ROOT"] = str(ARTWORK)
os.environ["REDIS_REQUIRED"] = "false"
os.environ["RADIUS_MOCK_USERS"] = json.dumps(
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
)

from app.core.config import get_settings

get_settings.cache_clear()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.bootstrap import seed_development_data
from app.db.base import Base
from app.models.content import Genre, Movie, Series
from app.models.content_translations import ContentTranslation
from app.services.catalog import utcnow
from app.utils.slug import normalize_slug

if DB.exists():
    DB.unlink()

engine = create_engine(f"sqlite:///{DB}", connect_args={"check_same_thread": False})
with engine.begin() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))
Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)
db = Session()
seed_development_data(db, include_demo_catalog=True)

genre_names = ["Action", "Comedy", "Drama", "Family", "Thriller"]
genres: dict[str, Genre] = {}
for name in genre_names:
    g = db.query(Genre).filter(Genre.name == name).one_or_none()
    if g is None:
        g = Genre(name=name, slug=normalize_slug(f"perf-{name}"))
        db.add(g)
        db.flush()
    genres[name] = g

now = utcnow()
for i in range(60):
    g = genres[genre_names[i % len(genre_names)]]
    m = Movie(
        title=f"Perf Stack Movie {i}",
        original_title=f"Perf Stack Movie {i}",
        slug=f"perf-stack-movie-{i}",
        description=f"Overview for perf stack movie {i}.",
        short_description=f"Short {i}",
        release_year=2000 + (i % 24),
        duration_minutes=100 + i % 40,
        age_rating="PG",
        language="English",
        country="USA" if i % 5 else "Afghanistan",
        imdb_rating=6.5 + (i % 30) / 10,
        status="published",
        published_at=now,
        is_featured=i < 6,
        is_trending=i % 5 == 0,
        views=2000 - i * 3,
        dubbed=["Persian"] if i % 4 == 0 else [],
        poster_url=f"https://image.tmdb.org/t/p/original/perf{i}.jpg",
        backdrop_url=f"https://image.tmdb.org/t/p/original/perfbg{i}.jpg",
    )
    m.genre_links = [g]
    db.add(m)
    db.flush()
    db.add(
        ContentTranslation(
            entity_type="movie",
            entity_id=m.id,
            locale="fa",
            field_key="title",
            value=f"فیلم پرف {i}",
            source="tmdb",
        )
    )

for i in range(15):
    g = genres[genre_names[i % len(genre_names)]]
    s = Series(
        title=f"Perf Stack Series {i}",
        original_title=f"Perf Stack Series {i}",
        slug=f"perf-stack-series-{i}",
        description=f"Series overview {i}",
        short_description=f"Series short {i}",
        release_year=2012 + i,
        age_rating="PG",
        language="English",
        country="USA",
        imdb_rating=7.0,
        status="published",
        published_at=now,
        views=800 - i,
        airing_status="Ended",
        poster_url=f"https://image.tmdb.org/t/p/original/series{i}.jpg",
    )
    s.genre_links = [g]
    db.add(s)

db.commit()
db.close()

meta = {
    "database_url": f"sqlite:///{DB}",
    "frontend_dist": os.environ["FRONTEND_DIST"],
    "media_root": str(MEDIA),
    "artwork_root": str(ARTWORK),
    "subscriber_user": "mobin_user_001",
    "subscriber_password": "fixture-pass-ok",
    "jwt_secret": os.environ["JWT_SECRET"],
}
(ROOT / "meta.json").write_text(json.dumps(meta, indent=2))
print(json.dumps(meta, indent=2))
