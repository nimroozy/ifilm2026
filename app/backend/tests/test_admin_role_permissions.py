"""Least-privilege demo role matrix + API gates (Train T0 Ready)."""

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


def _admin_headers(db_session, *, username: str, permissions: list[str]) -> dict[str, str]:
    role = AdminRole(name=f"role-{username}", permissions=list(permissions))
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username=username,
        email=f"{username}@example.com",
        full_name=username,
        hashed_password=hash_password("password-123456"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    token = create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})
    return {"Authorization": f"Bearer {token}"}


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
    assert "users" not in perms


def test_media_manager_owns_pipeline_not_users_or_publish():
    perms = _by_role()["Media Manager"]
    assert _has(perms, "upload.manage")
    assert _has(perms, "processing.manage")
    assert _has(perms, "streaming.manage")
    assert _has(perms, "streaming.read")
    assert "catalog.publish" not in perms
    assert "catalog.edit" not in perms
    assert "movies.manage" not in perms
    assert "users" not in perms
    assert "system_updates.manage" not in perms


def test_reviewer_review_only_no_media_edit():
    perms = _by_role()["Reviewer"]
    assert _has(perms, "streaming.read")
    assert not _has(perms, "streaming.manage")
    assert "catalog.review" in perms
    assert "catalog.approve" in perms
    assert not _has(perms, "upload.manage")
    assert not _has(perms, "processing.manage")
    assert "catalog.edit" not in perms
    assert "movies.manage" not in perms


def test_publisher_publish_only_no_delete_media():
    perms = _by_role()["Publisher"]
    assert _has(perms, "streaming.read")
    assert not _has(perms, "streaming.manage")
    assert "catalog.publish" in perms
    assert not _has(perms, "upload.manage")
    assert not _has(perms, "processing.manage")
    assert "users" not in perms


def test_catalog_manager_cannot_upload_media(client, db_session, monkeypatch):
    monkeypatch.setenv("ENABLE_UPLOADS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    headers = _admin_headers(
        db_session,
        username="cm-no-upload",
        permissions=list(_by_role()["Catalog Manager"]),
    )
    resp = client.post(
        "/api/admin/media/sessions",
        headers=headers,
        json={
            "filename": "clip.mp4",
            "size_bytes": 10,
            "mime_type": "video/mp4",
            "category": "originals",
        },
    )
    assert resp.status_code == 403
    get_settings.cache_clear()


def test_reviewer_cannot_edit_media_tracks(client, db_session, monkeypatch):
    monkeypatch.setenv("ENABLE_MEDIA_PROCESSING", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    headers = _admin_headers(
        db_session,
        username="rev-no-edit",
        permissions=list(_by_role()["Reviewer"]),
    )
    resp = client.post(
        "/api/admin/media/assets/00000000-0000-0000-0000-000000000099/tracks",
        headers=headers,
        json={"track_type": "audio", "language_code": "en"},
    )
    assert resp.status_code == 403
    get_settings.cache_clear()


def test_publisher_cannot_delete_assets(client, db_session, monkeypatch):
    monkeypatch.setenv("ENABLE_UPLOADS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    headers = _admin_headers(
        db_session,
        username="pub-no-delete",
        permissions=list(_by_role()["Publisher"]),
    )
    resp = client.post(
        "/api/admin/media/assets/00000000-0000-0000-0000-000000000099/delete",
        headers=headers,
        json={},
    )
    assert resp.status_code == 403
    get_settings.cache_clear()


def test_media_manager_cannot_manage_users():
    """Media Manager must not receive user-administration capabilities."""
    perms = _by_role()["Media Manager"]
    assert "users" not in perms
    assert "branches" not in perms
    assert "settings" not in perms
    assert "system_updates.manage" not in perms
    # Bare "movies" would alias to movies.manage — ensure read-only catalog context.
    assert "movies" not in perms
    assert not _has(perms, "movies.manage")
    assert _has(perms, "movies.read")


def test_admin_playback_requires_streaming_read(client, db_session, monkeypatch):
    """Admins without streaming.read cannot open customer playback sessions."""
    monkeypatch.setenv("ENABLE_LOCAL_STREAMING", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    headers = _admin_headers(
        db_session,
        username="no-stream-admin",
        permissions=["movies.read", "dashboard"],
    )
    resp = client.post(
        "/api/playback/sessions",
        headers=headers,
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

    headers = _admin_headers(
        db_session,
        username="stream-read-admin",
        permissions=["streaming.read"],
    )
    resp = client.post(
        "/api/playback/sessions",
        headers=headers,
        json={"media_asset_id": "00000000-0000-0000-0000-000000000099"},
    )
    assert resp.status_code == 404
    get_settings.cache_clear()
