"""Admin-facing system update orchestration (no root shell)."""

from __future__ import annotations

import html
import json
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import verify_password
from app.models.admin import AdminUser
from app.models.system_update import SystemUpdateEvent, SystemUpdateJob
from app.services.update_agent_client import (
    UpdateAgentClient,
    UpdateAgentError,
    get_update_agent_client,
)

ACTIVE_STATES = frozenset(
    {
        "queued",
        "available",
        "preflight",
        "backing_up",
        "downloading",
        "verifying",
        "draining",
        "installing",
        "migrating",
        "restarting",
        "health_checking",
        "rollback_running",
    }
)

_SAFE_ERROR = re.compile(r"(password|secret|token|key|credential)=[^\s]+", re.I)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _safe_error(message: str | None) -> str | None:
    if not message:
        return None
    cleaned = _SAFE_ERROR.sub(r"\1=REDACTED", message)
    return cleaned[:512]


def _sanitize_notes(notes: str | None) -> str:
    if not notes:
        return ""
    # Release notes are displayed as text; escape HTML to prevent XSS.
    return html.escape(notes)[:20_000]


def _add_event(db: Session, job_id: str, event_type: str, detail: str | None = None) -> None:
    db.add(
        SystemUpdateEvent(
            job_id=job_id,
            event_type=event_type,
            detail=_safe_error(detail) if detail else None,
        )
    )


def job_to_dict(job: SystemUpdateJob, events: list[SystemUpdateEvent] | None = None) -> dict[str, Any]:
    return {
        "id": job.id,
        "state": job.state,
        "channel": job.channel,
        "current_version": job.current_version,
        "target_version": job.target_version,
        "actor_admin_id": job.actor_admin_id,
        "backup_id": job.backup_id,
        "previous_migration_head": job.previous_migration_head,
        "resulting_migration_head": job.resulting_migration_head,
        "release_commit_sha": job.release_commit_sha,
        "preflight_ok": job.preflight_ok,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "rollback_result": job.rollback_result,
        "agent_job_id": job.agent_job_id,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "events": [
            {
                "event_type": e.event_type,
                "detail": e.detail,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in (events or [])
        ],
    }


def require_recent_password(admin: AdminUser, password: str) -> None:
    if not password or not verify_password(password, admin.hashed_password):
        raise PermissionError("reauthentication_failed")


def _active_job(db: Session) -> SystemUpdateJob | None:
    return (
        db.query(SystemUpdateJob)
        .filter(SystemUpdateJob.state.in_(tuple(ACTIVE_STATES)))
        .order_by(SystemUpdateJob.started_at.desc())
        .first()
    )


def _read_local_manifest(settings: Settings) -> dict[str, Any]:
    path = (settings.ifilm_version_file or "").strip()
    if not path:
        return {}
    try:
        p = Path(path)
        if not p.is_file():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def get_version_info(settings: Settings | None = None, client: UpdateAgentClient | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    local = _read_local_manifest(settings)
    version = str(local.get("version") or settings.app_version or "0.0.0-dev")
    commit = str(local.get("commit_sha") or settings.app_commit_sha or "unknown")
    build_date = local.get("published_at") or settings.app_build_date or None
    migration_head = str(local.get("migration_head") or settings.app_migration_head or "") or None
    channel = str(local.get("channel") or settings.update_channel or "stable")
    if client is not None or settings.update_agent_shared_secret:
        try:
            agent = client or get_update_agent_client()
            current = agent.call("get_current_version", {})
            version = str(current.get("version") or version)
            commit = str(current.get("commit_sha") or commit)
            migration_head = str(current.get("migration_head") or migration_head or "")
            channel = str(current.get("channel") or channel)
            build_date = current.get("published_at") or build_date
        except UpdateAgentError:
            pass
    return {
        "version": version,
        "build_commit": commit,
        "build_date": build_date,
        "migration_head": migration_head,
        "deployment_mode": settings.app_env,
        "update_channel": channel,
        "maintenance_mode": bool(settings.maintenance_mode),
    }


def check_for_updates(
    db: Session,
    admin: AdminUser,
    *,
    channel: str | None = None,
    client: UpdateAgentClient | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    ch = (channel or settings.update_channel or "stable").strip().lower()
    agent = client or get_update_agent_client()
    result = agent.call("check_latest_release", {"channel": ch})
    latest = result.get("latest")
    if isinstance(latest, dict) and latest.get("notes") is not None:
        latest = {**latest, "notes": _sanitize_notes(str(latest.get("notes") or ""))}
        result["latest"] = latest
    _add_event(
        db,
        _ensure_audit_job(db, admin, "check", ch, result).id,
        "check",
        f"update_available={result.get('update_available')}",
    )
    db.commit()
    return {
        "update_available": bool(result.get("update_available")),
        "channel": ch,
        "current": result.get("current") or {},
        "latest": result.get("latest"),
    }


def _ensure_audit_job(
    db: Session, admin: AdminUser, action: str, channel: str, result: dict[str, Any]
) -> SystemUpdateJob:
    current = (result.get("current") or {}).get("version")
    target = None
    latest = result.get("latest")
    if isinstance(latest, dict):
        target = latest.get("version")
    job = SystemUpdateJob(
        id=str(uuid.uuid4()),
        state="available" if result.get("update_available") else "completed",
        channel=channel,
        current_version=str(current) if current else None,
        target_version=str(target) if target else None,
        actor_admin_id=admin.id,
        started_at=_utcnow(),
        finished_at=_utcnow() if action == "check" else None,
        release_commit_sha=((latest or {}) if isinstance(latest, dict) else {}).get("commit_sha")
        if isinstance(latest, dict)
        else None,
    )
    # Don't persist every check as a long-lived active job; mark check-only completed.
    if action == "check":
        job.state = "check_recorded"
        job.finished_at = _utcnow()
    db.add(job)
    db.flush()
    return job


def run_preflight(
    db: Session,
    admin: AdminUser,
    *,
    client: UpdateAgentClient | None = None,
) -> dict[str, Any]:
    agent = client or get_update_agent_client()
    check = agent.call("check_latest_release", {"channel": get_settings().update_channel})
    payload: dict[str, Any] = {"channel": get_settings().update_channel}
    latest = check.get("latest") or {}
    if isinstance(latest, dict):
        if latest.get("manifest_url"):
            payload["manifest_url"] = latest["manifest_url"]
        if latest.get("signature_url"):
            payload["signature_url"] = latest["signature_url"]
    result = agent.call("run_preflight", payload)
    job = SystemUpdateJob(
        id=str(uuid.uuid4()),
        state="preflight" if result.get("ok") else "preflight_failed",
        channel=get_settings().update_channel,
        current_version=str((check.get("current") or {}).get("version") or ""),
        target_version=str(latest.get("version") or "") if isinstance(latest, dict) else None,
        actor_admin_id=admin.id,
        preflight_ok=bool(result.get("ok")),
        started_at=_utcnow(),
        finished_at=_utcnow(),
    )
    db.add(job)
    db.flush()
    _add_event(db, job.id, "preflight", f"ok={result.get('ok')}")
    db.commit()
    checks = [
        {"name": c.get("name", ""), "passed": bool(c.get("passed")), "detail": str(c.get("detail") or "")}
        for c in (result.get("checks") or [])
        if isinstance(c, dict)
    ]
    return {"ok": bool(result.get("ok")), "checks": checks, "checked_at": result.get("checked_at")}


def create_backup(
    db: Session,
    admin: AdminUser,
    *,
    client: UpdateAgentClient | None = None,
) -> dict[str, Any]:
    agent = client or get_update_agent_client()
    result = agent.call("create_backup", {}, timeout=1900.0)
    job = SystemUpdateJob(
        id=str(uuid.uuid4()),
        state="completed",
        channel=get_settings().update_channel,
        actor_admin_id=admin.id,
        backup_id=str(result.get("backup_id") or ""),
        started_at=_utcnow(),
        finished_at=_utcnow(),
    )
    db.add(job)
    db.flush()
    _add_event(db, job.id, "backup", job.backup_id)
    db.commit()
    # Never return filesystem path to API clients.
    return {
        "backup_id": str(result.get("backup_id") or ""),
        "created_at": result.get("created_at"),
        "validated": bool(result.get("validated")),
    }


def start_install(
    db: Session,
    admin: AdminUser,
    *,
    password: str,
    confirm: bool,
    target_version: str | None = None,
    client: UpdateAgentClient | None = None,
    background: bool = True,
) -> dict[str, Any]:
    require_recent_password(admin, password)
    if not confirm:
        raise ValueError("confirmation_required")
    existing = _active_job(db)
    if existing is not None:
        raise RuntimeError("concurrent_update")

    agent = client or get_update_agent_client()
    check = agent.call("check_latest_release", {"channel": get_settings().update_channel})
    latest = check.get("latest")
    if not check.get("update_available") or not isinstance(latest, dict):
        raise RuntimeError("no_update_available")
    if target_version and str(latest.get("version")) != target_version.lstrip("v"):
        raise RuntimeError("target_mismatch")

    job = SystemUpdateJob(
        id=str(uuid.uuid4()),
        state="queued",
        channel=get_settings().update_channel,
        current_version=str((check.get("current") or {}).get("version") or ""),
        target_version=str(latest.get("version") or ""),
        actor_admin_id=admin.id,
        release_commit_sha=str(latest.get("commit_sha") or "") or None,
        started_at=_utcnow(),
    )
    db.add(job)
    db.flush()
    _add_event(db, job.id, "install_queued", job.target_version)
    db.commit()
    job_id = job.id

    payload = {
        "target_version": latest.get("version"),
        "manifest_url": latest.get("manifest_url"),
        "signature_url": latest.get("signature_url"),
        "archive_url": latest.get("archive_url"),
        "channel": get_settings().update_channel,
    }

    def _run() -> None:
        from app.db.session import SessionLocal

        session = SessionLocal()
        try:
            _execute_install(session, job_id, payload, agent_factory=lambda: client or get_update_agent_client())
        finally:
            session.close()

    if background:
        threading.Thread(target=_run, name=f"ifilm-update-{job_id}", daemon=True).start()
    else:
        _execute_install(db, job_id, payload, agent_factory=lambda: agent)
    return get_job(db, job_id, admin)


def _execute_install(
    db: Session,
    job_id: str,
    payload: dict[str, Any],
    *,
    agent_factory,
) -> None:
    job = db.get(SystemUpdateJob, job_id)
    if job is None:
        return
    job.state = "installing"
    _add_event(db, job_id, "install_started", None)
    db.commit()
    try:
        agent = agent_factory()
        result = agent.call("install_verified_release", payload, timeout=7200.0)
        job = db.get(SystemUpdateJob, job_id)
        if job is None:
            return
        job.agent_job_id = str(result.get("job_id") or "") or None
        job.state = str(result.get("state") or "completed")
        job.backup_id = result.get("backup_id") or job.backup_id
        if result.get("error"):
            err = result["error"]
            job.error_code = str(err.get("code") or "failed")[:64]
            job.error_message = _safe_error(str(err.get("message") or ""))
        if job.state in {"completed", "rolled_back"}:
            job.finished_at = _utcnow()
            ver = get_version_info(client=agent)
            job.resulting_migration_head = ver.get("migration_head")
        _add_event(db, job_id, "install_finished", job.state)
        db.commit()
    except UpdateAgentError as exc:
        job = db.get(SystemUpdateJob, job_id)
        if job is None:
            return
        job.state = "failed"
        job.error_code = exc.code[:64]
        job.error_message = _safe_error(exc.message)
        job.finished_at = _utcnow()
        _add_event(db, job_id, "install_failed", job.error_code)
        db.commit()
    except Exception:  # noqa: BLE001
        job = db.get(SystemUpdateJob, job_id)
        if job is None:
            return
        job.state = "failed"
        job.error_code = "internal"
        job.error_message = "update failed"
        job.finished_at = _utcnow()
        _add_event(db, job_id, "install_failed", "internal")
        db.commit()


def get_job(db: Session, job_id: str, admin: AdminUser, *, client: UpdateAgentClient | None = None) -> dict[str, Any]:
    job = db.get(SystemUpdateJob, job_id)
    if job is None:
        raise LookupError("not_found")
    # IDOR hardening: non-super users may only see their own jobs. Super Admin has manage.
    perms = set((admin.role.permissions if admin.role else None) or [])
    if "system_updates.manage" not in perms and job.actor_admin_id != admin.id:
        raise PermissionError("forbidden")
    if job.agent_job_id and job.state in ACTIVE_STATES:
        try:
            agent = client or get_update_agent_client()
            progress = agent.call("query_update_progress", {"job_id": job.agent_job_id})
            state = str(progress.get("state") or job.state)
            if state != job.state:
                job.state = state
                db.commit()
        except UpdateAgentError:
            pass
    events = (
        db.query(SystemUpdateEvent)
        .filter(SystemUpdateEvent.job_id == job_id)
        .order_by(SystemUpdateEvent.created_at.asc())
        .all()
    )
    return job_to_dict(job, events)


def list_history(db: Session, *, limit: int = 50) -> dict[str, Any]:
    q = db.query(SystemUpdateJob).order_by(SystemUpdateJob.started_at.desc())
    total = q.count()
    jobs = q.limit(min(max(limit, 1), 200)).all()
    return {"items": [job_to_dict(j) for j in jobs], "total": total}


def start_rollback(
    db: Session,
    admin: AdminUser,
    *,
    password: str,
    confirm: bool,
    job_id: str | None = None,
    confirm_database_restore: bool = False,
    client: UpdateAgentClient | None = None,
) -> dict[str, Any]:
    require_recent_password(admin, password)
    if not confirm:
        raise ValueError("confirmation_required")
    existing = _active_job(db)
    if existing is not None and existing.id != job_id:
        raise RuntimeError("concurrent_update")

    target = db.get(SystemUpdateJob, job_id) if job_id else None
    if target is None:
        target = (
            db.query(SystemUpdateJob)
            .filter(SystemUpdateJob.state.in_(("completed", "migration_failed", "health_check_failed", "failed")))
            .order_by(SystemUpdateJob.started_at.desc())
            .first()
        )
    if target is None:
        raise LookupError("not_found")

    # Irreversible DB rollback requires explicit confirmation (manifest-driven).
    if target.rollback_result == "requires_database_restore" and not confirm_database_restore:
        raise ValueError("database_restore_confirmation_required")

    agent = client or get_update_agent_client()
    target.state = "rollback_running"
    _add_event(db, target.id, "rollback_started", None)
    db.commit()
    try:
        result = agent.call(
            "rollback_last_update",
            {"job_id": target.agent_job_id or target.id, "reason": "admin_requested"},
            timeout=3600.0,
        )
        target.state = str(result.get("state") or "rolled_back")
        target.rollback_result = target.state
        target.finished_at = _utcnow()
        _add_event(db, target.id, "rollback_finished", target.state)
        db.commit()
    except UpdateAgentError as exc:
        target.state = "rollback_failed"
        target.rollback_result = "rollback_failed"
        target.error_code = exc.code[:64]
        target.error_message = _safe_error(exc.message)
        target.finished_at = _utcnow()
        _add_event(db, target.id, "rollback_failed", target.error_code)
        db.commit()
    return get_job(db, target.id, admin, client=client)
