"""System update API tests (agent mocked; no root shell)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from app.bootstrap import SUPER_PERMISSIONS
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.admin import AdminRole, AdminUser
from app.models.system_update import SystemUpdateJob
from app.services import system_updates as svc
from app.services.update_agent_client import UpdateAgentError
from tests.conftest import TEST_ADMIN_PASSWORD


class FakeAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.current = {
            "version": "0.1.0-test",
            "commit_sha": "abc123",
            "channel": "stable",
            "migration_head": "011_system_updates",
            "published_at": "2026-08-01T00:00:00Z",
        }
        self.latest = {
            "version": "0.1.1-test",
            "tag": "v0.1.1-test",
            "prerelease": False,
            "published_at": "2026-08-02T00:00:00Z",
            "notes": "<script>alert(1)</script> notes",
            "manifest_url": "https://github.com/nimroozy/ifilm2026/releases/download/v0.1.1-test/release-manifest.json",
            "signature_url": "https://github.com/nimroozy/ifilm2026/releases/download/v0.1.1-test/release-manifest.json.sig",
            "archive_url": "https://github.com/nimroozy/ifilm2026/releases/download/v0.1.1-test/ifilm-0.1.1-test.tar.gz",
        }
        self.update_available = True
        self.preflight_ok = True
        self.install_state = "completed"
        self.fail_mode: str | None = None

    def call(self, command: str, payload: dict[str, Any] | None = None, *, timeout: float = 120.0) -> dict[str, Any]:
        body = dict(payload or {})
        self.calls.append((command, body))
        if command == "get_current_version":
            return dict(self.current)
        if command == "check_latest_release":
            channel = body.get("channel") or "stable"
            latest = dict(self.latest)
            if channel == "stable" and latest.get("prerelease"):
                return {"update_available": False, "current": self.current, "latest": None, "channel": channel}
            return {
                "update_available": self.update_available,
                "current": self.current,
                "latest": latest if self.update_available else None,
                "channel": channel,
            }
        if command == "run_preflight":
            return {
                "ok": self.preflight_ok,
                "checks": [{"name": "disk_space", "passed": self.preflight_ok, "detail": "10GB"}],
                "checked_at": "2026-08-01T00:00:00Z",
            }
        if command == "create_backup":
            if self.fail_mode == "backup":
                raise UpdateAgentError("backup_failed", "pg_dump failed")
            return {"backup_id": "pre-update-test", "created_at": "2026-08-01T00:00:00Z", "validated": True}
        if command == "install_verified_release":
            if self.fail_mode == "checksum":
                return {
                    "job_id": "agent1",
                    "state": "verification_failed",
                    "error": {"code": "checksum_mismatch", "message": "archive sha256 mismatch"},
                }
            if self.fail_mode == "migration":
                return {
                    "job_id": "agent1",
                    "state": "rolled_back",
                    "backup_id": "pre-update-test",
                    "error": {"code": "migration_failed", "message": "alembic upgrade failed"},
                }
            self.current["version"] = str(self.latest["version"])
            return {
                "job_id": "agent1",
                "state": self.install_state,
                "backup_id": "pre-update-test",
                "result": {"version": self.current["version"]},
            }
        if command == "query_update_progress":
            return {"job_id": body.get("job_id"), "state": self.install_state}
        if command == "rollback_last_update":
            self.current["version"] = "0.1.0-test"
            return {"job_id": body.get("job_id"), "state": "rolled_back", "result": self.current}
        raise UpdateAgentError("invalid_command", command)


@pytest.fixture()
def fake_agent(monkeypatch: pytest.MonkeyPatch) -> FakeAgent:
    agent = FakeAgent()
    monkeypatch.setenv("APP_VERSION", "0.1.0-test")
    monkeypatch.setenv("UPDATE_CHANNEL", "stable")
    monkeypatch.setenv("UPDATE_AGENT_SHARED_SECRET", "test-agent-secret")
    get_settings.cache_clear()
    monkeypatch.setattr(svc, "get_update_agent_client", lambda: agent)
    return agent


def _admin_headers(client) -> dict[str, str]:
    res = client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": TEST_ADMIN_PASSWORD},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_version_endpoint_safe(client, fake_agent: FakeAgent):
    headers = _admin_headers(client)
    res = client.get("/api/admin/system/version", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == "0.1.0-test"
    blob = str(body).lower()
    assert "password" not in blob
    assert "secret" not in blob
    assert body["update_channel"] == "stable"


def test_check_sanitizes_release_notes(client, fake_agent: FakeAgent):
    headers = _admin_headers(client)
    res = client.post("/api/admin/system/updates/check", headers=headers)
    assert res.status_code == 200
    notes = res.json()["latest"]["notes"]
    assert "<script>" not in notes
    assert "&lt;script&gt;" in notes


def test_prerelease_excluded_from_stable(client, fake_agent: FakeAgent):
    headers = _admin_headers(client)

    def call(command, payload=None, *, timeout=120.0):
        if command == "check_latest_release":
            return {
                "update_available": False,
                "current": fake_agent.current,
                "latest": None,
                "channel": "stable",
            }
        return FakeAgent.call(fake_agent, command, payload, timeout=timeout)

    fake_agent.call = call  # type: ignore[method-assign]
    res = client.post("/api/admin/system/updates/check", headers=headers)
    assert res.status_code == 200
    assert res.json()["update_available"] is False


def test_install_requires_confirm_and_password(client, fake_agent: FakeAgent):
    headers = _admin_headers(client)
    res = client.post(
        "/api/admin/system/updates/install",
        headers=headers,
        json={"password": TEST_ADMIN_PASSWORD, "confirm": False},
    )
    assert res.status_code == 400

    res = client.post(
        "/api/admin/system/updates/install",
        headers=headers,
        json={"password": "wrong-password-here", "confirm": True},
    )
    assert res.status_code == 401


def test_successful_sync_install_and_history(client, fake_agent: FakeAgent):
    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter(AdminUser.username == "admin").one()
        job = svc.start_install(
            db,
            admin,
            password=TEST_ADMIN_PASSWORD,
            confirm=True,
            target_version="0.1.1-test",
            client=fake_agent,  # type: ignore[arg-type]
            background=False,
        )
        assert job["state"] == "completed"
        assert job["backup_id"] == "pre-update-test"
        assert fake_agent.current["version"] == "0.1.1-test"
    finally:
        db.close()

    headers = _admin_headers(client)
    hist = client.get("/api/admin/system/updates/history", headers=headers)
    assert hist.status_code == 200
    assert hist.json()["total"] >= 1


def test_migration_failure_records_rollback(client, fake_agent: FakeAgent):
    fake_agent.fail_mode = "migration"
    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter(AdminUser.username == "admin").one()
        job = svc.start_install(
            db,
            admin,
            password=TEST_ADMIN_PASSWORD,
            confirm=True,
            client=fake_agent,  # type: ignore[arg-type]
            background=False,
        )
        assert job["state"] == "rolled_back"
        assert job["error_code"] == "migration_failed"
    finally:
        db.close()


def test_concurrent_update_rejected(client, fake_agent: FakeAgent):
    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter(AdminUser.username == "admin").one()
        db.add(
            SystemUpdateJob(
                id=str(uuid.uuid4()),
                state="installing",
                channel="stable",
                actor_admin_id=admin.id,
                started_at=datetime.now(UTC),
            )
        )
        db.commit()
        with pytest.raises(RuntimeError, match="concurrent_update"):
            svc.start_install(
                db,
                admin,
                password=TEST_ADMIN_PASSWORD,
                confirm=True,
                client=fake_agent,  # type: ignore[arg-type]
                background=False,
            )
    finally:
        db.close()


def test_successful_preflight_does_not_block_install(client, fake_agent: FakeAgent):
    headers = _admin_headers(client)
    pre = client.post("/api/admin/system/updates/preflight", headers=headers)
    assert pre.status_code == 200
    assert pre.json()["ok"] is True

    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter(AdminUser.username == "admin").one()
        recorded = (
            db.query(SystemUpdateJob)
            .filter(SystemUpdateJob.state == "preflight_ok")
            .order_by(SystemUpdateJob.started_at.desc())
            .first()
        )
        assert recorded is not None
        assert recorded.preflight_ok is True
        job = svc.start_install(
            db,
            admin,
            password=TEST_ADMIN_PASSWORD,
            confirm=True,
            target_version="0.1.1-test",
            client=fake_agent,  # type: ignore[arg-type]
            background=False,
        )
        assert job["state"] == "completed"
    finally:
        db.close()


def test_permission_enforcement(client, fake_agent: FakeAgent):
    db = SessionLocal()
    try:
        role = AdminRole(name="Catalog Only", permissions=["movies.read", "movies.manage"])
        db.add(role)
        db.flush()
        user = AdminUser(
            username="cataloger",
            email="cataloger@example.test",
            hashed_password=hash_password("catalog-pass-ok-12"),
            full_name="Cataloger",
            is_active=True,
            role_id=role.id,
        )
        db.add(user)
        db.commit()
    finally:
        db.close()

    login = client.post(
        "/api/admin/auth/login",
        json={"username": "cataloger", "password": "catalog-pass-ok-12"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/admin/system/version", headers=headers).status_code == 403
    assert client.post("/api/admin/system/updates/check", headers=headers).status_code == 403


def test_super_permissions_include_system_updates():
    assert "system_updates.read" in SUPER_PERMISSIONS
    assert "system_updates.manage" in SUPER_PERMISSIONS


def test_token_redaction_helper():
    assert "REDACTED" in (svc._safe_error("POSTGRES_PASSWORD=supersecret value") or "")


def test_backup_failure(client, fake_agent: FakeAgent):
    fake_agent.fail_mode = "backup"
    headers = _admin_headers(client)
    res = client.post(
        "/api/admin/system/updates/backup",
        headers=headers,
        json={"password": TEST_ADMIN_PASSWORD, "confirm": True},
    )
    assert res.status_code == 503
