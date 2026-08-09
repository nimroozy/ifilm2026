"""Publishing worker healthcheck must reflect real worker readiness (not API HTTP)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.workers import publishing as publishing_worker
from app.workers.publishing import run_healthcheck


def test_publishing_worker_healthcheck_ok(db_session):
    # db_session fixture ensures engine/session are bound for the test DB.
    assert run_healthcheck() == 0


def test_publishing_worker_healthcheck_missing_dependency(db_session):
    with patch.object(
        publishing_worker,
        "_required_dependencies_ok",
        side_effect=RuntimeError("DATABASE_URL is not configured"),
    ):
        assert run_healthcheck() == 1


def test_load_runtime_env_file_sets_missing_keys(tmp_path, monkeypatch):
    import builtins
    import os

    env_file = tmp_path / "runtime.env"
    env_file.write_text("DATABASE_URL=sqlite:///tmp/hc.db\nREDIS_URL=redis://x\n", encoding="utf-8")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    real_open = open

    def _open(path, *args, **kwargs):
        if path == "/run/ifilm/runtime.env":
            return real_open(env_file, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _open)
    publishing_worker._load_runtime_env_file()
    assert os.environ["DATABASE_URL"] == "sqlite:///tmp/hc.db"
    assert os.environ["REDIS_URL"] == "redis://x"


def test_publishing_worker_healthcheck_database_failure(db_session):
    with patch.object(publishing_worker, "_database_ok", side_effect=RuntimeError("db down")):
        assert run_healthcheck() == 1


def test_publishing_worker_healthcheck_queue_init_failure(db_session):
    with patch.object(publishing_worker, "_queue_consumer_ok", side_effect=RuntimeError("claim broken")):
        assert run_healthcheck() == 1


def test_publishing_worker_healthcheck_dependency_import_failure(db_session):
    with patch.object(
        publishing_worker,
        "_required_dependencies_ok",
        side_effect=ImportError("missing dependency"),
    ):
        assert run_healthcheck() == 1


def test_publishing_worker_cli_healthcheck_exit_code(db_session):
    with pytest.raises(SystemExit) as exc:
        publishing_worker.main(["--healthcheck"])
    assert exc.value.code == 0

    with patch.object(publishing_worker, "run_healthcheck", return_value=1):
        with pytest.raises(SystemExit) as exc:
            publishing_worker.main(["--healthcheck"])
        assert exc.value.code == 1
