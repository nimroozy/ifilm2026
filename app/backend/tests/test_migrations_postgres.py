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
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert "movies" in tables
    assert "admin_users" in tables
    assert "genres" in tables
    assert "seasons" in tables
    assert "media_assets" in tables
    assert "upload_sessions" in tables
    assert "system_update_jobs" in tables
    assert "system_update_events" in tables
    assert "app_settings" in tables
    assert "collections" in tables
    assert "collection_items" in tables
    assert version == "020_content_translations_v1"


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
        movie_slug = conn.execute(
            text("SELECT slug FROM movies WHERE title='Ordinary Film'")
        ).scalar_one()
        series_slug = conn.execute(
            text("SELECT slug FROM series WHERE title='Ordinary Show'")
        ).scalar_one()
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        null_imdb = conn.execute(
            text("SELECT COUNT(*) FROM movies WHERE imdb_id IS NULL")
        ).scalar_one()
    engine.dispose()
    assert movie_slug == "ordinary-film"
    assert series_slug == "ordinary-show"
    assert null_imdb >= 1
    assert version == "020_content_translations_v1"


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
        mixed = conn.execute(text("SELECT slug FROM movies WHERE title LIKE 'Mixed%'")).scalar_one()
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
        movie_nulls = conn.execute(
            text("SELECT COUNT(*) FROM movies WHERE imdb_id IS NULL")
        ).scalar_one()
        series_nulls = conn.execute(
            text("SELECT COUNT(*) FROM series WHERE imdb_id IS NULL")
        ).scalar_one()
    engine.dispose()
    assert movie_nulls >= 2
    assert series_nulls >= 1


def test_downgrade_catalog_not_supported(postgres_url):
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "003_catalog_admin").returncode == 0
    result = _run_alembic(postgres_url, "downgrade", "-1")
    assert result.returncode != 0
    assert (
        "not supported" in (result.stdout + result.stderr).lower()
        or "notimplemented" in (result.stdout + result.stderr).lower()
    )


def test_media_upload_migration_roundtrip(postgres_url):
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "003_catalog_admin").returncode == 0
    assert _run_alembic(postgres_url, "upgrade", "004_media_upload").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert "media_assets" in tables
    assert "upload_sessions" in tables
    assert version == "004_media_upload"

    assert _run_alembic(postgres_url, "downgrade", "003_catalog_admin").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert "media_assets" not in tables
    assert version == "003_catalog_admin"


def test_media_processing_migration_roundtrip(postgres_url):
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "004_media_upload").returncode == 0
    assert _run_alembic(postgres_url, "upgrade", "005_media_processing").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            )
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='media_assets'"
                )
            )
        }
    engine.dispose()
    assert "media_processing_jobs" in tables
    assert "media_processing_job_events" in tables
    assert "uq_media_processing_active_probe" in indexes
    assert "container_format" in cols
    assert "probe_json" in cols
    assert version == "005_media_processing"

    assert _run_alembic(postgres_url, "downgrade", "004_media_upload").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            )
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='media_assets'"
                )
            )
        }
    engine.dispose()
    assert "media_processing_jobs" not in tables
    assert "uq_media_processing_active_probe" not in indexes
    assert "container_format" not in cols
    assert "media_assets" in tables
    assert version == "004_media_upload"

    assert _run_alembic(postgres_url, "upgrade", "005_media_processing").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        indexes = {
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            )
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert "uq_media_processing_active_probe" in indexes
    assert version == "005_media_processing"


def test_hls_encoding_migration_roundtrip(postgres_url):
    """005 → 006 → 005 → 006 round-trip for HLS encoding schema."""
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "005_media_processing").returncode == 0
    assert _run_alembic(postgres_url, "upgrade", "006_hls_encoding").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            )
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        profile_count = conn.execute(
            text("SELECT COUNT(*) FROM media_encoding_profiles")
        ).scalar_one()
    engine.dispose()
    assert "media_encoding_profiles" in tables
    assert "media_packages" in tables
    assert "media_renditions" in tables
    assert "uq_media_processing_active_encode_hls" in indexes
    assert profile_count == 5
    assert version == "006_hls_encoding"

    assert _run_alembic(postgres_url, "downgrade", "005_media_processing").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            )
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert "media_encoding_profiles" not in tables
    assert "media_packages" not in tables
    assert "media_renditions" not in tables
    assert "uq_media_processing_active_encode_hls" not in indexes
    assert "media_processing_jobs" in tables
    assert version == "005_media_processing"

    assert _run_alembic(postgres_url, "upgrade", "006_hls_encoding").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        indexes = {
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            )
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        profile_count = conn.execute(
            text("SELECT COUNT(*) FROM media_encoding_profiles")
        ).scalar_one()
    engine.dispose()
    assert "uq_media_processing_active_encode_hls" in indexes
    assert profile_count == 5
    assert version == "006_hls_encoding"


def test_streaming_service_migration_roundtrip(postgres_url):
    """006 → 007 → 006 → 007 round-trip with active-package backfill."""
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "006_hls_encoding").returncode == 0
    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        # Minimal asset + packages for backfill scenarios.
        conn.execute(
            text(
                """
                INSERT INTO media_assets (
                  id, original_filename, stored_filename, mime_type, extension,
                  size_bytes, category, upload_status, processing_status, storage_backend
                ) VALUES (
                  'asset-1', 'a.mp4', 'a.mp4', 'video/mp4', '.mp4',
                  1, 'originals', 'completed', 'completed', 'local'
                )
                """
            )
        )
        # older completed, newer completed, failed, cancelled, encoding
        for pkg_id, status, completed in [
            ("pkg-old", "completed", "2026-01-01 00:00:00+00"),
            ("pkg-new", "completed", "2026-06-01 00:00:00+00"),
            ("pkg-fail", "failed", None),
            ("pkg-cancel", "cancelled", None),
            ("pkg-enc", "encoding", None),
        ]:
            conn.execute(
                text(
                    """
                    INSERT INTO media_packages (
                      id, media_asset_id, package_type, status, segment_duration_seconds,
                      rendition_count, completed_at, created_at
                    ) VALUES (
                      :id, 'asset-1', 'hls_vod', :status, 6, 0,
                      CAST(:completed AS timestamptz), NOW()
                    )
                    """
                ),
                {"id": pkg_id, "status": status, "completed": completed},
            )
        # Asset with no completed package
        conn.execute(
            text(
                """
                INSERT INTO media_assets (
                  id, original_filename, stored_filename, mime_type, extension,
                  size_bytes, category, upload_status, processing_status, storage_backend
                ) VALUES (
                  'asset-2', 'b.mp4', 'b.mp4', 'video/mp4', '.mp4',
                  1, 'originals', 'completed', 'none', 'local'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO media_packages (
                  id, media_asset_id, package_type, status, segment_duration_seconds,
                  rendition_count, created_at
                ) VALUES (
                  'pkg-pending', 'asset-2', 'hls_vod', 'pending', 6, 0, NOW()
                )
                """
            )
        )
    engine.dispose()

    assert _run_alembic(postgres_url, "upgrade", "007_streaming_service").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        active = list(
            conn.execute(
                text(
                    "SELECT id, is_active FROM media_packages WHERE media_asset_id='asset-1' ORDER BY id"
                )
            )
        )
        asset2_active = conn.execute(
            text("SELECT COUNT(*) FROM media_packages WHERE media_asset_id='asset-2' AND is_active")
        ).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            )
        }
    engine.dispose()
    assert version == "007_streaming_service"
    assert "media_playback_sessions" in tables
    assert "uq_media_packages_one_active_hls" in indexes
    active_map = {row[0]: row[1] for row in active}
    assert active_map["pkg-new"] is True
    assert active_map["pkg-old"] is False
    assert active_map["pkg-fail"] is False
    assert active_map["pkg-cancel"] is False
    assert active_map["pkg-enc"] is False
    assert asset2_active == 0

    assert _run_alembic(postgres_url, "downgrade", "006_hls_encoding").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='media_packages'"
                )
            )
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert "media_playback_sessions" not in tables
    assert "is_active" not in cols
    assert version == "006_hls_encoding"

    assert _run_alembic(postgres_url, "upgrade", "007_streaming_service").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert version == "007_streaming_service"


def test_publishing_workflow_migration_roundtrip(postgres_url):
    """007 → 008 → 007 → 008 round-trip for publishing workflow schema."""
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "007_streaming_service").returncode == 0

    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO movies (
                  title, original_title, slug, description, short_description,
                  age_rating, language, country, poster_url, backdrop_url, trailer_url,
                  status, is_featured, is_trending, director, "cast", audio, subtitles,
                  qualities, dubbed, views, created_at, updated_at
                ) VALUES (
                  'Pub Mig', '', 'pub-mig', '', '',
                  '', '', '', '', '', '',
                  'draft', false, false, '', '[]', '[]', '[]',
                  '[]', '[]', 0, NOW(), NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO series (
                  title, original_title, slug, description, short_description,
                  age_rating, language, country, poster_url, backdrop_url, trailer_url,
                  status, airing_status, is_featured, is_trending, audio, subtitles,
                  dubbed, new_episode, views, created_at, updated_at
                ) VALUES (
                  'Series Mig', '', 'series-mig', '', '',
                  '', '', '', '', '', '',
                  'draft', 'Ongoing', false, false, '[]', '[]',
                  '[]', false, 0, NOW(), NOW()
                )
                """
            )
        )
        series_id = conn.execute(text("SELECT id FROM series WHERE slug='series-mig'")).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO seasons (
                  series_id, season_number, title, description, poster_url, status,
                  created_at, updated_at
                ) VALUES (
                  :sid, 1, 'S1', '', '', 'draft', NOW(), NOW()
                )
                """
            ),
            {"sid": series_id},
        )
    engine.dispose()

    assert _run_alembic(postgres_url, "upgrade", "008_publishing_workflow").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        movie_cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='movies'"
                )
            )
        }
        season_cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='seasons'"
                )
            )
        }
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        pub_version = conn.execute(
            text("SELECT publication_version FROM movies WHERE slug='pub-mig'")
        ).scalar_one()
    engine.dispose()
    assert version == "008_publishing_workflow"
    assert "media_publication_events" in tables
    assert "scheduled_publish_at" in movie_cols
    assert "published_at" in season_cols
    assert "publication_version" in movie_cols
    assert pub_version == 0

    assert _run_alembic(postgres_url, "downgrade", "007_streaming_service").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        movie_cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='movies'"
                )
            )
        }
        season_cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='seasons'"
                )
            )
        }
    engine.dispose()
    assert version == "007_streaming_service"
    assert "media_publication_events" not in tables
    assert "scheduled_publish_at" not in movie_cols
    assert "published_at" not in season_cols

    assert _run_alembic(postgres_url, "upgrade", "008_publishing_workflow").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert version == "008_publishing_workflow"


def test_watch_history_migration_roundtrip(postgres_url):
    """008 → 009 → 008 → 009 round-trip for watch progress schema."""
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "008_publishing_workflow").returncode == 0

    assert _run_alembic(postgres_url, "upgrade", "009_watch_history").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='user_watch_progress'"
                )
            )
        }
    engine.dispose()
    assert version == "009_watch_history"
    assert "user_watch_progress" in tables
    assert "watch_history" not in tables
    assert "media_asset_id" in cols
    assert "last_event_at" in cols
    assert "progress_percent" in cols

    assert _run_alembic(postgres_url, "downgrade", "008_publishing_workflow").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
    engine.dispose()
    assert version == "008_publishing_workflow"
    assert "user_watch_progress" not in tables
    assert "watch_history" in tables

    assert _run_alembic(postgres_url, "upgrade", "009_watch_history").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert version == "009_watch_history"


def test_subscriber_entitlements_migration_roundtrip(postgres_url):
    """009 → 010 → 009 → 010 round-trip for subscriber entitlement schema."""
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "009_watch_history").returncode == 0
    assert _run_alembic(postgres_url, "upgrade", "010_subscriber_entitlements").returncode == 0

    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='subscribers'"
                )
            )
        }
    engine.dispose()
    assert version == "010_subscriber_entitlements"
    assert "subscriber_entitlement_snapshots" in tables
    assert "subscriber_device_sessions" in tables
    assert "subscriber_refresh_tokens" in tables
    assert "identity_provider" in cols
    assert "external_subject" in cols

    assert _run_alembic(postgres_url, "downgrade", "009_watch_history").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
    engine.dispose()
    assert version == "009_watch_history"
    assert "subscriber_entitlement_snapshots" not in tables
    assert "subscriber_device_sessions" not in tables
    assert "subscriber_refresh_tokens" not in tables

    assert _run_alembic(postgres_url, "upgrade", "010_subscriber_entitlements").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert version == "010_subscriber_entitlements"


def test_external_media_playability_migration_roundtrip(postgres_url):
    """014 → 015 → 014 → 015 round-trip for external media + credit fields."""
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "014_tmdb_demo_metadata").returncode == 0
    assert _run_alembic(postgres_url, "upgrade", "015_external_media_playability").returncode == 0

    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        media_cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='media_assets'"
                )
            )
        }
        movie_cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='movies'"
                )
            )
        }
        session_nullable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name='media_playback_sessions' AND column_name='media_package_id'"
            )
        ).scalar_one()
        indexes = {
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            )
        }
    engine.dispose()
    assert version == "015_external_media_playability"
    assert {
        "source_type",
        "external_url",
        "external_kind",
        "external_content_type",
        "external_content_length",
        "external_accept_ranges",
        "external_validated_at",
        "external_is_primary",
        "external_protection_mode",
        "external_acknowledged_at",
        "external_acknowledged_by_admin_id",
    }.issubset(media_cols)
    assert {"producer", "writer", "studio"}.issubset(movie_cols)
    assert session_nullable == "YES"
    assert "ix_media_assets_source_type" in indexes
    assert "ix_media_assets_external_is_primary" in indexes

    assert _run_alembic(postgres_url, "downgrade", "014_tmdb_demo_metadata").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        media_cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='media_assets'"
                )
            )
        }
        movie_cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='movies'"
                )
            )
        }
        session_nullable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name='media_playback_sessions' AND column_name='media_package_id'"
            )
        ).scalar_one()
    engine.dispose()
    assert version == "014_tmdb_demo_metadata"
    assert "source_type" not in media_cols
    assert "external_url" not in media_cols
    assert "producer" not in movie_cols
    assert session_nullable == "NO"

    assert _run_alembic(postgres_url, "upgrade", "015_external_media_playability").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        media_cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='media_assets'"
                )
            )
        }
    engine.dispose()
    assert version == "015_external_media_playability"
    assert "source_type" in media_cols


def test_collections_v1_migration_roundtrip(postgres_url):
    """015 → 016 → 015 → 016 round-trip for collections tables."""
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "015_external_media_playability").returncode == 0
    assert _run_alembic(postgres_url, "upgrade", "019_media_upload_reliability_v1").returncode == 0

    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            )
        }
        collection_cols = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='collections'"
                )
            )
        }
    engine.dispose()
    assert version == "019_media_upload_reliability_v1"
    assert "collections" in tables
    assert "collection_items" in tables
    assert {
        "title",
        "slug",
        "collection_type",
        "status",
        "visibility",
        "poster_url",
        "backdrop_url",
        "is_featured",
        "demo_owned",
        "demo_seed_version",
    }.issubset(collection_cols)
    assert "uq_collections_slug" in indexes or any("slug" in i for i in indexes)
    assert "uq_collection_items_movie" in indexes
    assert "uq_collection_items_series" in indexes

    assert _run_alembic(postgres_url, "downgrade", "015_external_media_playability").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
    engine.dispose()
    assert version == "015_external_media_playability"
    assert "collections" not in tables
    assert "collection_items" not in tables

    assert _run_alembic(postgres_url, "upgrade", "019_media_upload_reliability_v1").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
    engine.dispose()
    assert version == "019_media_upload_reliability_v1"
    assert "collections" in tables


def test_alembic_heads_single(postgres_url):
    result = _run_alembic(postgres_url, "heads")
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [ln for ln in (result.stdout + result.stderr).splitlines() if ln.strip()]
    head_lines = [ln for ln in lines if "020_content_translations_v1" in ln]
    assert head_lines, result.stdout + result.stderr
    assert sum(1 for ln in lines if ln.strip().startswith("020_content_translations_v1")) >= 1


def test_media_upload_reliability_migration_roundtrip(postgres_url):
    """018 → 019 → 018 → head for media_admin_events audit table."""
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "018_movie_detail_experience_v1").returncode == 0
    assert _run_alembic(postgres_url, "upgrade", "019_media_upload_reliability_v1").returncode == 0

    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
    engine.dispose()
    assert version == "019_media_upload_reliability_v1"
    assert "media_admin_events" in tables
    assert "movie_cast_credits" in tables

    assert _run_alembic(postgres_url, "downgrade", "018_movie_detail_experience_v1").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
    engine.dispose()
    assert version == "018_movie_detail_experience_v1"
    assert "media_admin_events" not in tables
    assert "movie_cast_credits" in tables

    assert _run_alembic(postgres_url, "upgrade", "head").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
    engine.dispose()
    assert version == "020_content_translations_v1"
    assert "media_admin_events" in tables
    assert "content_translations" in tables


def test_content_translations_migration_roundtrip(postgres_url):
    """019 → 020 → 019 → 020 for content_translations table."""
    _reset_schema(postgres_url)
    assert _run_alembic(postgres_url, "upgrade", "019_media_upload_reliability_v1").returncode == 0
    assert _run_alembic(postgres_url, "upgrade", "020_content_translations_v1").returncode == 0

    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
    engine.dispose()
    assert version == "020_content_translations_v1"
    assert "content_translations" in tables
    assert "media_admin_events" in tables

    assert _run_alembic(postgres_url, "downgrade", "019_media_upload_reliability_v1").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
    engine.dispose()
    assert version == "019_media_upload_reliability_v1"
    assert "content_translations" not in tables
    assert "media_admin_events" in tables

    assert _run_alembic(postgres_url, "upgrade", "020_content_translations_v1").returncode == 0
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
    engine.dispose()
    assert version == "020_content_translations_v1"
    assert "content_translations" in tables
