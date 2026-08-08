"""Super Admin permission merge must be idempotent and additive."""

from __future__ import annotations

from app.bootstrap import SUPER_PERMISSIONS, ensure_super_admin_permissions
from app.models.admin import AdminRole


def test_ensure_super_admin_permissions_merges_content_requests(db_session):
    role = db_session.query(AdminRole).filter(AdminRole.name == "Super Admin").one()
    role.permissions = ["dashboard"]
    db_session.add(role)
    db_session.flush()

    assert ensure_super_admin_permissions(db_session) is True
    db_session.refresh(role)
    assert "content_requests.read" in role.permissions
    assert "content_requests.manage" in role.permissions
    assert set(SUPER_PERMISSIONS).issubset(set(role.permissions))

    assert ensure_super_admin_permissions(db_session) is False
