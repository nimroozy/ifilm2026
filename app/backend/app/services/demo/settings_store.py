"""Persist demo marker keys in app_settings."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.app_settings import AppSetting
from app.services.demo.constants import (
    SETTING_DEMO_COMMIT,
    SETTING_DEMO_INSTALLED,
    SETTING_DEMO_INSTALLED_AT,
    SETTING_DEMO_VERSION,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value, updated_at=utcnow())
        db.add(row)
    else:
        row.value = value
        row.updated_at = utcnow()
        db.add(row)


def get_setting(db: Session, key: str) -> str | None:
    row = db.get(AppSetting, key)
    return None if row is None else row.value


def mark_demo_installed(db: Session, *, version: str, commit_sha: str, installed_at: str) -> None:
    set_setting(db, SETTING_DEMO_INSTALLED, "true")
    set_setting(db, SETTING_DEMO_VERSION, version)
    set_setting(db, SETTING_DEMO_COMMIT, commit_sha)
    set_setting(db, SETTING_DEMO_INSTALLED_AT, installed_at)


def clear_demo_markers(db: Session) -> None:
    for key in (
        SETTING_DEMO_INSTALLED,
        SETTING_DEMO_VERSION,
        SETTING_DEMO_COMMIT,
        SETTING_DEMO_INSTALLED_AT,
    ):
        row = db.get(AppSetting, key)
        if row is not None:
            db.delete(row)
