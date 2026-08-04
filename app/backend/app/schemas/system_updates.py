from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SystemVersionOut(BaseModel):
    version: str
    build_commit: str
    build_date: str | None = None
    migration_head: str | None = None
    deployment_mode: str
    update_channel: str
    maintenance_mode: bool = False
    integrity: dict[str, Any] | None = None
    update_blocked: bool = False


class UpdateCheckOut(BaseModel):
    update_available: bool
    channel: str
    current: dict[str, Any]
    latest: dict[str, Any] | None = None


class PreflightCheckOut(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class PreflightOut(BaseModel):
    ok: bool
    checks: list[PreflightCheckOut]
    checked_at: str | None = None


class ConfirmPasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    confirm: bool = False
    channel: str | None = None


class InstallUpdateIn(ConfirmPasswordIn):
    target_version: str | None = None
    confirm: bool = False


class RollbackIn(ConfirmPasswordIn):
    job_id: str | None = None
    confirm_database_restore: bool = False


class UpdateJobOut(BaseModel):
    id: str
    state: str
    channel: str
    current_version: str | None = None
    target_version: str | None = None
    actor_admin_id: int | None = None
    backup_id: str | None = None
    previous_migration_head: str | None = None
    resulting_migration_head: str | None = None
    release_commit_sha: str | None = None
    preflight_ok: bool | None = None
    error_code: str | None = None
    error_message: str | None = None
    rollback_result: str | None = None
    agent_job_id: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)


class UpdateHistoryOut(BaseModel):
    items: list[UpdateJobOut]
    total: int


class BackupOut(BaseModel):
    backup_id: str
    created_at: str | None = None
    validated: bool = False
