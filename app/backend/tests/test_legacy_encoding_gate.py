"""Legacy EncodingJob path must stay quarantined outside local legacy-dev."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.services.legacy_encoding import (
    legacy_encoding_allowed,
    legacy_encoding_block_reason,
    require_legacy_encoding_allowed,
)
from app.services.media_processing.lifecycle import CANONICAL_STATES, canonical_media_state


def test_canonical_states_match_pipeline_doc():
    assert CANONICAL_STATES == (
        "uploaded",
        "probing",
        "ready",
        "encoding",
        "packaged",
        "published",
        "failed",
    )


def test_canonical_media_state_transitions():
    class _A:
        def __init__(self, **kw):
            self.upload_status = kw.get("upload_status", "completed")
            self.processing_status = kw.get("processing_status", "none")
            self.probed_at = kw.get("probed_at")

    assert canonical_media_state(_A(upload_status="completed", probed_at=None)) == "uploaded"
    assert (
        canonical_media_state(
            _A(probed_at=None),
            active_job_type="probe",
            active_job_status="running",
        )
        == "probing"
    )
    assert canonical_media_state(_A(probed_at="2026-01-01")) == "ready"
    assert (
        canonical_media_state(
            _A(probed_at="2026-01-01"),
            active_job_type="encode_hls",
            active_job_status="queued",
        )
        == "encoding"
    )
    assert (
        canonical_media_state(_A(probed_at="2026-01-01"), has_active_completed_package=True)
        == "packaged"
    )
    assert (
        canonical_media_state(
            _A(probed_at="2026-01-01"),
            has_active_completed_package=True,
            catalog_published=True,
        )
        == "published"
    )
    assert canonical_media_state(_A(processing_status="failed")) == "failed"


@pytest.mark.parametrize("env", ["production", "prod", "staging"])
def test_legacy_encoding_hard_blocked_in_prod_staging(env):
    settings = Settings(
        app_env=env,
        enable_encoding=True,
        jwt_secret="x" * 32,
        database_url="sqlite://",
    )
    assert legacy_encoding_allowed(settings) is False
    reason = legacy_encoding_block_reason(settings)
    assert reason is not None
    assert "disabled" in reason.lower() or "PIPELINE" in reason
    with pytest.raises(HTTPException) as exc:
        require_legacy_encoding_allowed(settings)
    assert exc.value.status_code == 503


def test_legacy_encoding_requires_flag_in_development():
    off = Settings(
        app_env="development",
        enable_encoding=False,
        jwt_secret="x" * 32,
        database_url="sqlite://",
    )
    assert legacy_encoding_allowed(off) is False
    on = Settings(
        app_env="development",
        enable_encoding=True,
        jwt_secret="x" * 32,
        database_url="sqlite://",
    )
    assert legacy_encoding_allowed(on) is True


@pytest.mark.asyncio
async def test_arq_process_encoding_job_refuses_when_blocked(monkeypatch):
    from app.workers import tasks as worker_tasks

    monkeypatch.setattr(
        worker_tasks,
        "legacy_encoding_allowed",
        lambda settings=None: False,
    )
    monkeypatch.setattr(
        worker_tasks,
        "legacy_encoding_block_reason",
        lambda settings=None: "blocked for test",
    )
    monkeypatch.setattr(worker_tasks, "get_engine", lambda: None)
    result = await worker_tasks.process_encoding_job({}, 1)
    assert result["ok"] is False
    assert result["error"] == "legacy_encoding_blocked"
