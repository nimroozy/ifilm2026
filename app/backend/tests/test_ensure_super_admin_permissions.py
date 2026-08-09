"""Super Admin permission bootstrap must be idempotent and additive."""

from __future__ import annotations

from app.bootstrap import (
    REQUIRED_SUPER_ADMIN_PERMISSIONS,
    SUPER_PERMISSIONS,
    ensure_super_admin_permissions,
)
from app.models.admin import AdminRole


def test_required_content_request_permissions_are_in_super_set():
    assert set(REQUIRED_SUPER_ADMIN_PERMISSIONS).issubset(set(SUPER_PERMISSIONS))


def test_fresh_database_creates_super_admin_with_content_requests(db_session):
    db_session.query(AdminRole).filter(AdminRole.name == "Super Admin").delete()
    db_session.flush()
    assert db_session.query(AdminRole).filter(AdminRole.name == "Super Admin").one_or_none() is None

    assert ensure_super_admin_permissions(db_session) is True
    role = db_session.query(AdminRole).filter(AdminRole.name == "Super Admin").one()
    for perm in REQUIRED_SUPER_ADMIN_PERMISSIONS:
        assert perm in role.permissions
    assert set(SUPER_PERMISSIONS).issubset(set(role.permissions))


def test_existing_database_repairs_missing_permissions(db_session):
    role = db_session.query(AdminRole).filter(AdminRole.name == "Super Admin").one()
    role.permissions = ["dashboard", "movies.read"]
    db_session.add(role)
    db_session.flush()

    assert ensure_super_admin_permissions(db_session) is True
    db_session.refresh(role)
    assert "dashboard" in role.permissions  # never destructive
    assert "movies.read" in role.permissions
    for perm in REQUIRED_SUPER_ADMIN_PERMISSIONS:
        assert perm in role.permissions


def test_repeated_startup_creates_no_duplicates(db_session):
    role = db_session.query(AdminRole).filter(AdminRole.name == "Super Admin").one()
    role.permissions = ["dashboard"]
    db_session.add(role)
    db_session.flush()

    assert ensure_super_admin_permissions(db_session) is True
    db_session.refresh(role)
    first = list(role.permissions)
    assert ensure_super_admin_permissions(db_session) is False
    db_session.refresh(role)
    second = list(role.permissions)
    assert first == second
    assert len(second) == len(set(second))
    assert second.count("content_requests.read") == 1
    assert second.count("content_requests.manage") == 1


def test_api_startup_merge_via_lifespan_path(db_session):
    """Simulate the lifespan merge path: commit when changed, no-op when stable."""
    role = db_session.query(AdminRole).filter(AdminRole.name == "Super Admin").one()
    role.permissions = [p for p in (role.permissions or []) if not str(p).startswith("content_requests.")]
    db_session.add(role)
    db_session.commit()

    changed = ensure_super_admin_permissions(db_session)
    assert changed is True
    db_session.commit()
    db_session.refresh(role)
    for perm in REQUIRED_SUPER_ADMIN_PERMISSIONS:
        assert perm in role.permissions

    assert ensure_super_admin_permissions(db_session) is False
