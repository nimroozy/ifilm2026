"""Publishing worker healthcheck must not depend on API HTTP."""

from __future__ import annotations

from app.workers.publishing import run_healthcheck


def test_publishing_worker_healthcheck_ok(db_session):
    # db_session fixture ensures engine/session are bound for the test DB.
    assert run_healthcheck() == 0
