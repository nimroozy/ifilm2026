"""PostgreSQL Alembic migration integration tests.

These tests require DATABASE_URL pointing at PostgreSQL (provided in CI).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def _postgres_url() -> str | None:
    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url or "postgres" not in url:
        return None
    # Avoid sqlite unit-test URL.
    if url.startswith("sqlite"):
        return None
    return url


@pytest.fixture(scope="module")
def postgres_url():
    url = _postgres_url()
    if not url:
        pytest.skip("PostgreSQL TEST_DATABASE_URL/DATABASE_URL not configured")
    return url


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
    engine.dispose()
    assert "movies" in tables
    assert "admin_users" in tables
    assert "alembic_version" in tables


def test_postgresql_migration_from_previous_revision(postgres_url):
    _reset_schema(postgres_url)
    first = _run_alembic(postgres_url, "upgrade", "001_initial")
    assert first.returncode == 0, first.stdout + first.stderr
    second = _run_alembic(postgres_url, "upgrade", "head")
    assert second.returncode == 0, second.stdout + second.stderr

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
    assert "ix_movies_title" in indexes
    assert version == "002_movies_title_idx"
