"""Least-privilege demo role matrix (Train T0)."""

from __future__ import annotations

from app.core.deps import PERMISSION_ALIASES
from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.services.demo.constants import ADMIN_FIXTURES


def _by_role() -> dict[str, set[str]]:
    return {row["role_name"]: set(row["permissions"]) for row in ADMIN_FIXTURES}


def _has(perms: set[str], need: str) -> bool:
    allowed = PERMISSION_ALIASES.get(need, frozenset({need}))
    return not perms.isdisjoint(allowed)


def test_demo_roles_include_media_manager():
    roles = _by_role()
    assert "Media Manager" in roles
    assert "Catalog Manager" in roles
    assert "Reviewer" in roles
    assert "Publisher" in roles


def test_catalog_manager_has_no_media_pipeline_perms():
    perms = _by_role()["Catalog Manager"]
    assert not _has(perms, "upload.manage")
    assert not _has(perms, "upload.read")
    assert not _has(perms, "processing.manage")
    assert not _has(perms, "processing.read")
    assert not _has(perms, "streaming.read")
    assert not _has(perms, "streaming.manage")
    assert "catalog.edit" in perms
    assert _has(perms, "movies.manage")


def test_media_manager_owns_pipeline_not_publish():
    perms = _by_role()["Media Manager"]
    assert _has(perms, "upload.manage")
    assert _has(perms, "processing.manage")
    assert _has(perms, "streaming.manage")
    assert _has(perms, "streaming.read")
    assert "catalog.publish" not in perms
    assert "catalog.edit" not in perms
    assert "movies.manage" not in perms


def test_reviewer_can_preview_not_manage_sessions():
    perms = _by_role()["Reviewer"]
    assert _has(perms, "streaming.read")
    assert not _has(perms, "streaming.manage")
    assert "catalog.review" in perms
    assert not _has(perms, "upload.manage")


def test_publisher_loses_streaming_manage():
    perms = _by_role()["Publisher"]
    assert _has(perms, "streaming.read")
    assert not _has(perms, "streaming.manage")
    assert "catalog.publish" in perms


def test_admin_playback_requires_streaming_read(client, db_session, monkeypatch):
    """Admins without streaming.read cannot open customer playback sessions."""
    monkeypatch.setenv("ENABLE_LOCAL_STREAMING", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    role = AdminRole(name="no-stream-role", permissions=["movies.read", "dashboard"])
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username="no-stream-admin",
        email="nostream@example.com",
        full_name="No Stream",
        hashed_password=hash_password("password-123456"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    token = create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})
    resp = client.post(
        "/api/playback/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"media_asset_id": "00000000-0000-0000-0000-000000000099"},
    )
    assert resp.status_code == 403
    assert "permission" in str(resp.json().get("detail", "")).lower()
    get_settings.cache_clear()


def test_admin_with_streaming_read_passes_permission_gate(client, db_session, monkeypatch):
    """streaming.read clears the admin gate (asset may still 404)."""
    monkeypatch.setenv("ENABLE_LOCAL_STREAMING", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    role = AdminRole(name="stream-read-role", permissions=["streaming.read"])
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username="stream-read-admin",
        email="streamread@example.com",
        full_name="Stream Read",
        hashed_password=hash_password("password-123456"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    token = create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})
    resp = client.post(
        "/api/playback/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"media_asset_id": "00000000-0000-0000-0000-000000000099"},
    )
    # Permission gate passed; missing asset → 404 (not 403 insufficient permissions).
    assert resp.status_code == 404
    get_settings.cache_clear()
