"""PostgreSQL Alembic migration integration tests.

These tests require TEST_DATABASE_URL pointing at PostgreSQL.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_003 = ROOT / "alembic" / "versions" / "003_catalog_administration.py"


def _postgres_url() -> str | None:
    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url or "postgres" not in url:
        return None
    if url.startswith("sqlite"):
        return None
    return url


@pytest.fixture(scope="module")
def postgres_url():
    url = _postgres_url()
    if not url:
        pytest.skip("PostgreSQL TEST_DATABASE_URL/DATABASE_URL not configured")
    return url


def _load_migration_003():
    spec = importlib.util.spec_from_file_location("catalog_admin_migration_003", MIGRATION_003)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["APP_ENV"] = "test"
    env["JWT_SECRET"] = "migration-test-jwt-secret-value-32ch"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _reset_schema(url: str) -> None:
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _insert_legacy_movie(conn, *, title: str, **extra) -> int:
    cols = {
        "title": title,
        "original_title": extra.get("original_title", ""),
        "year": extra.get("year", 2024),
        "duration": extra.get("duration", 100),
        "rating": extra.get("rating", 7.0),
        "age_rating": "PG",
        "genres": "[]",
        "country": "",
        "language": "",
        "director": "",
        "cast": "[]",
        "description": "",
        "poster": "",
        "backdrop": "",
        "audio": "[]",
        "subtitles": "[]",
        "qualities": "[]",
        "dubbed": "[]",
        "featured": False,
        "views": 0,
        "published": True,
    }
    result = conn.execute(
        text(
            """
            INSERT INTO movies (
              title, original_title, year, duration, rating, age_rating, genres,
              country, language, director, "cast", description, poster, backdrop,
              audio, subtitles, qualities, dubbed, featured, views, published
            ) VALUES (
              :title, :original_title, :year, :duration, :rating, :age_rating,
              CAST(:genres AS json), :country, :language, :director, CAST(:cast AS json),
              :description, :poster, :backdrop, CAST(:audio AS json), CAST(:subtitles AS json),
              CAST(:qualities AS json), CAST(:dubbed AS json), :featured, :views, :published
            ) RETURNING id
            """
        ),
        cols,
    )
    return int(result.scalar_one())


def _insert_legacy_series(conn, *, title: str) -> int:
    result = conn.execute(
        text(
            """
            INSERT INTO series (
              title, original_title, year, rating, age_rating, genres, country, language,
              seasons, episode_count, status, description, poster, backdrop,
              audio, subtitles, dubbed, new_episode, views, published
            ) VALUES (
              :title, '', 2024, 7.0, 'PG', CAST('[]' AS json), '', '',
              1, 0, 'Ongoing', '', '', '',
              CAST('[]' AS json), CAST('[]' AS json), CAST('[]' AS json), false, 0, true
            ) RETURNING id
            """
        ),
        {"title": title},
    )
    return int(result.scalar_one())


def _assert_valid_slugs(slugs: list[str]) -> None:
    assert slugs
    assert all(s and s.strip() for s in slugs)
    assert all(len(s) <= 280 for s in slugs)
    assert len(slugs) == len(set(slugs))


def test_postgresql_migration_succeeds(postgres_url):
    _reset_schema(postgres_url)
    result = _run_alembic(postgres_url, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr

    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert "movies" in tables
    assert "admin_users" in tables
    assert "genres" in tables
    assert "seasons" in tables
    assert "media_assets" in tables
    assert "upload_sessions" in tables
    assert version == "004_media_upload"


def test_postgresql_migration_from_previous_revision(postgres_url):
    _reset_schema(postgres_url)
    first = _run_alembic(postgres_url, "upgrade", "002_movies_title_idx")
    assert first.returncode == 0, first.stdout + first.stderr

    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        _insert_legacy_movie(conn, title="Ordinary Film")
        _insert_legacy_series(conn, title="Ordinary Show")
    engine.dispose()

    second = _run_alembic(postgres_url, "upgrade", "head")
    assert second.returncode == 0, second.stdout + second.stderr

    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        movie_slug = conn.execute(text("SELECT slug FROM movies WHERE title='Ordinary Film'")).scalar_one()
        series_slug = conn.execute(text("SELECT slug FROM series WHERE title='Ordinary Show'")).scalar_one()
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        null_imdb = conn.execute(text("SELECT COUNT(*) FROM movies WHERE imdb_id IS NULL")).scalar_one()
    engine.dispose()
    assert movie_slug == "ordinary-film"
    assert series_slug == "ordinary-show"
    assert null_imdb >= 1
    assert version == "004_media_upload"


def test_002_to_head_duplicate_and_messy_titles(postgres_url):
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "002_movies_title_idx").returncode == 0

    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        _insert_legacy_movie(conn, title="Same Title")
        _insert_legacy_movie(conn, title="Same Title")
        _insert_legacy_movie(conn, title="same title")
        _insert_legacy_movie(conn, title="Same  Title!")
        _insert_legacy_movie(conn, title="")
        _insert_legacy_movie(conn, title="   ")
        _insert_legacy_series(conn, title="Dup Series")
        _insert_legacy_series(conn, title="Dup Series")
        _insert_legacy_series(conn, title="dup-series")
    engine.dispose()

    result = _run_alembic(postgres_url, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr

    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        movie_slugs = [r[0] for r in conn.execute(text("SELECT slug FROM movies ORDER BY id"))]
        series_slugs = [r[0] for r in conn.execute(text("SELECT slug FROM series ORDER BY id"))]
        emptyish = conn.execute(
            text("SELECT COUNT(*) FROM movies WHERE slug IS NULL OR btrim(slug)=''")
        ).scalar_one()
    engine.dispose()

    assert emptyish == 0
    _assert_valid_slugs(movie_slugs)
    _assert_valid_slugs(series_slugs)
    assert any(s == "same-title" for s in movie_slugs)
    assert sum(1 for s in movie_slugs if s.startswith("same-title")) >= 3
    assert any(s.startswith("item") for s in movie_slugs)


def test_002_to_head_unicode_titles(postgres_url):
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "002_movies_title_idx").returncode == 0

    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        _insert_legacy_movie(conn, title="آخرین کاروان")
        _insert_legacy_movie(conn, title="شهر زمرد")
        _insert_legacy_series(conn, title="بازار")
        _insert_legacy_movie(conn, title="Mixed کاروان Caravan")
    engine.dispose()

    result = _run_alembic(postgres_url, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr

    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        rows = list(conn.execute(text("SELECT title, slug FROM movies ORDER BY id")))
        _assert_valid_slugs([slug for _, slug in rows])
        mixed = conn.execute(
            text("SELECT slug FROM movies WHERE title LIKE 'Mixed%'")
        ).scalar_one()
        assert "caravan" in mixed
    engine.dispose()


def test_002_to_head_long_title_slug_collisions(postgres_url):
    """Collision suffixes must survive the 280-char slug limit."""
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "002_movies_title_idx").returncode == 0

    long_a = "A" * 400
    long_same_prefix_a = ("B" * 280) + "TAILONE"
    long_same_prefix_b = ("B" * 280) + "TAILTWO"

    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        # Legacy title column is VARCHAR(255); widen only in this test so we can
        # exercise slug truncation near the 280-char unique slug limit.
        conn.execute(text("ALTER TABLE movies ALTER COLUMN title TYPE VARCHAR(512)"))
        id_long_1 = _insert_legacy_movie(conn, title=long_a)
        id_long_2 = _insert_legacy_movie(conn, title=long_a)
        id_prefix_1 = _insert_legacy_movie(conn, title=long_same_prefix_a)
        id_prefix_2 = _insert_legacy_movie(conn, title=long_same_prefix_b)
        id_uni_1 = _insert_legacy_movie(conn, title="آخرین کاروان")
        id_uni_2 = _insert_legacy_movie(conn, title="آخرین کاروان")
        id_empty_1 = _insert_legacy_movie(conn, title="")
        id_empty_2 = _insert_legacy_movie(conn, title="   ")
        id_punct_1 = _insert_legacy_movie(conn, title="!!! ???")
        id_punct_2 = _insert_legacy_movie(conn, title="---...")
    engine.dispose()

    result = _run_alembic(postgres_url, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr

    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        rows = list(conn.execute(text("SELECT id, slug FROM movies ORDER BY id")))
    engine.dispose()

    by_id = {row_id: slug for row_id, slug in rows}
    slugs = [slug for _, slug in rows]
    _assert_valid_slugs(slugs)

    # Identical overlong titles: winner keeps bare truncated slug; loser keeps -<id>.
    winner_long, loser_long = sorted([id_long_1, id_long_2])
    assert by_id[winner_long] == "a" * 280
    assert by_id[loser_long].endswith(f"-{loser_long}")
    assert len(by_id[loser_long]) == 280

    # Distinct tails that share the same 280-char normalized prefix collide on bare slug.
    winner_prefix, loser_prefix = sorted([id_prefix_1, id_prefix_2])
    assert by_id[winner_prefix] == "b" * 280
    assert by_id[loser_prefix].endswith(f"-{loser_prefix}")
    assert len(by_id[loser_prefix]) <= 280

    # Unicode-only / empty / punctuation-only all normalize to base ``item``.
    item_ids = sorted([id_uni_1, id_uni_2, id_empty_1, id_empty_2, id_punct_1, id_punct_2])
    assert by_id[item_ids[0]] == "item"
    for item_id in item_ids[1:]:
        assert by_id[item_id] == f"item-{item_id}"
        assert by_id[item_id].endswith(f"-{item_id}")


def test_duplicate_imdb_guard_without_migration_hooks(postgres_url):
    """Prepare conflicting imdb_id values after the column exists, then run the guard.

    Does not rely on environment variables or test-only migration branches.
    """
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "002_movies_title_idx").returncode == 0

    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        _insert_legacy_movie(conn, title="Film A")
        _insert_legacy_movie(conn, title="Film B")
        # Mid-upgrade shape: imdb_id exists (as 003 adds it) before uniqueness.
        conn.execute(text("ALTER TABLE movies ADD COLUMN imdb_id VARCHAR(32)"))
        conn.execute(text("UPDATE movies SET imdb_id = 'tt9999999'"))

        migration = _load_migration_003()
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            with pytest.raises(DBAPIError) as exc_info:
                migration._assert_no_duplicate_imdb("movies")
    engine.dispose()

    combined = str(exc_info.value).lower()
    assert "imdb_id" in combined
    assert "tt9999999" in combined or "duplicate" in combined


def test_multiple_null_imdb_ids_allowed(postgres_url):
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "002_movies_title_idx").returncode == 0
    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        _insert_legacy_movie(conn, title="Null IMDb 1")
        _insert_legacy_movie(conn, title="Null IMDb 2")
        _insert_legacy_series(conn, title="Null IMDb Series")
    engine.dispose()

    result = _run_alembic(postgres_url, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr

    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        movie_nulls = conn.execute(text("SELECT COUNT(*) FROM movies WHERE imdb_id IS NULL")).scalar_one()
        series_nulls = conn.execute(text("SELECT COUNT(*) FROM series WHERE imdb_id IS NULL")).scalar_one()
    engine.dispose()
    assert movie_nulls >= 2
    assert series_nulls >= 1


def test_downgrade_catalog_not_supported(postgres_url):
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "003_catalog_admin").returncode == 0
    result = _run_alembic(postgres_url, "downgrade", "-1")
    assert result.returncode != 0
    assert "not supported" in (result.stdout + result.stderr).lower() or "notimplemented" in (
        result.stdout + result.stderr
    ).lower()


def test_media_upload_migration_roundtrip(postgres_url):
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "003_catalog_admin").returncode == 0
    assert _run_alembic(postgres_url, "upgrade", "head").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert "media_assets" in tables
    assert "upload_sessions" in tables
    assert version == "004_media_upload"

    assert _run_alembic(postgres_url, "downgrade", "-1").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert "media_assets" not in tables
    assert version == "003_catalog_admin"


def test_alembic_heads_single(postgres_url):
    result = _run_alembic(postgres_url, "heads")
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [ln.strip() for ln in (result.stdout + result.stderr).splitlines() if ln.strip()]
    head_lines = [ln for ln in lines if "004_media_upload" in ln]
    assert head_lines, result.stdout + result.stderr
    assert sum(1 for ln in lines if ln.startswith("004_media_upload")) >= 1
