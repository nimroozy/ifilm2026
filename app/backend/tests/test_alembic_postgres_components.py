"""Prove Alembic works with production-like POSTGRES_* env (no DATABASE_URL)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def _base_url() -> str | None:
    return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


@pytest.fixture(scope="module")
def postgres_components():
    url = _base_url()
    if not url or not str(url).startswith("postgresql"):
        pytest.skip("PostgreSQL TEST_DATABASE_URL/DATABASE_URL not configured")
    parsed = make_url(url)
    # Sanity: can connect
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    engine.dispose()
    return {
        "POSTGRES_USER": parsed.username or "",
        "POSTGRES_PASSWORD": parsed.password or "",
        "POSTGRES_HOST": parsed.host or "127.0.0.1",
        "POSTGRES_PORT": str(parsed.port or 5432),
        "POSTGRES_DB": parsed.database or "",
    }


def _run_alembic_without_database_url(components: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # Force POSTGRES_* resolution: clear URL overrides from the parent process / .env.
    env.pop("DATABASE_URL", None)
    env.pop("TEST_DATABASE_URL", None)
    env["DATABASE_URL"] = ""
    env.update(components)
    env["PYTHONPATH"] = str(ROOT)
    # Ensure settings don't pull a stale DATABASE_URL from .env
    env["APP_ENV"] = "test"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_alembic_current_without_database_url(postgres_components):
    result = _run_alembic_without_database_url(postgres_components, "current")
    combined = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0, combined
    # Never leak password in alembic output
    assert postgres_components["POSTGRES_PASSWORD"] not in combined
    assert "DATABASE_URL=" not in combined


def test_alembic_history_and_heads_without_database_url(postgres_components):
    history = _run_alembic_without_database_url(postgres_components, "history")
    assert history.returncode == 0, history.stdout + history.stderr
    assert "012_system_update_notes" in (history.stdout + history.stderr)

    heads = _run_alembic_without_database_url(postgres_components, "heads")
    assert heads.returncode == 0, heads.stdout + heads.stderr
    assert "020_content_translations_v1" in (heads.stdout + heads.stderr)


def test_alembic_upgrade_head_without_database_url(postgres_components):
    from app.core.db_url import database_url_from_postgres_env

    url = database_url_from_postgres_env(postgres_components)
    assert url
    # Isolate from other suites that may leave a partial schema.
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()

    result = _run_alembic_without_database_url(postgres_components, "upgrade", "head")
    combined = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0, combined
    assert postgres_components["POSTGRES_PASSWORD"] not in combined

    engine = create_engine(url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert version == "020_content_translations_v1"
