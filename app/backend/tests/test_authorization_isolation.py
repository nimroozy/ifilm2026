"""Admin authorization isolation for catalog endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from jose import jwt

# Keep local copies — do not import tests.conftest (dual module vs pytest plugin).
TEST_ADMIN_PASSWORD = "unit-test-admin-pass-ok"
TEST_FIXTURE_USER = "mobin_user_001"
TEST_FIXTURE_PASSWORD = "fixture-pass-ok"


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_admin(db_session, *, username: str, permissions: list[str], active: bool = True) -> str:
    role = AdminRole(name=f"role-{username}", permissions=permissions)
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username=username,
        email=f"{username}@example.test",
        full_name=username,
        hashed_password=hash_password("limited-admin-pass-ok"),
        role_id=role.id,
        is_active=active,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})


def test_admin_endpoints_require_auth(client):
    assert client.get("/api/admin/movies").status_code == 401
    assert client.post("/api/admin/movies", json={"title": "X"}).status_code == 401
    assert client.get("/api/admin/genres").status_code == 401


def test_subscriber_token_forbidden_on_admin(client):
    login = client.post(
        "/api/auth/login",
        json={"username": TEST_FIXTURE_USER, "password": TEST_FIXTURE_PASSWORD},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert client.get("/api/admin/movies", headers=_headers(token)).status_code == 403
    assert client.post(
        "/api/admin/movies",
        headers=_headers(token),
        json={"title": "Nope"},
    ).status_code == 403


def test_movies_read_cannot_mutate(client, db_session):
    token = _make_admin(db_session, username="reader", permissions=["movies.read"])
    headers = _headers(token)
    listed = client.get("/api/admin/movies", headers=headers)
    assert listed.status_code == 200
    created = client.post(
        "/api/admin/movies",
        headers=headers,
        json={"title": "Should Fail", "slug": "should-fail"},
    )
    assert created.status_code == 403


def test_movies_manage_cannot_manage_genres(client, db_session):
    token = _make_admin(db_session, username="movie-mgr", permissions=["movies.manage"])
    headers = _headers(token)
    assert (
        client.post(
            "/api/admin/movies",
            headers=headers,
            json={"title": "Managed", "slug": "managed-movie"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/admin/genres",
            headers=headers,
            json={"name": "Blocked Genre", "slug": "blocked-genre"},
        ).status_code
        == 403
    )
    assert client.delete("/api/admin/genres/1", headers=headers).status_code == 403


def test_series_manage_does_not_grant_genre_management(client, db_session):
    token = _make_admin(db_session, username="series-mgr", permissions=["series.manage"])
    headers = _headers(token)
    assert (
        client.post(
            "/api/admin/series",
            headers=headers,
            json={"title": "Series Managed", "slug": "series-managed"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/admin/genres",
            headers=headers,
            json={"name": "No Genre", "slug": "no-genre"},
        ).status_code
        == 403
    )


def test_admin_without_required_permission_forbidden(client, db_session):
    token = _make_admin(db_session, username="cdn-only", permissions=["cdn"])
    headers = _headers(token)
    assert client.get("/api/admin/movies", headers=headers).status_code == 403
    assert client.get("/api/admin/series", headers=headers).status_code == 403
    assert client.get("/api/admin/genres", headers=headers).status_code == 403


def test_legacy_movies_alias_grants_movie_manage_not_genres(client, db_session):
    token = _make_admin(db_session, username="legacy-movies", permissions=["movies"])
    headers = _headers(token)
    assert client.get("/api/admin/movies", headers=headers).status_code == 200
    assert (
        client.post(
            "/api/admin/movies",
            headers=headers,
            json={"title": "Legacy Movie", "slug": "legacy-movie"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/admin/genres",
            headers=headers,
            json={"name": "Legacy Blocked", "slug": "legacy-blocked"},
        ).status_code
        == 403
    )


def test_disabled_admin_rejected(client, db_session):
    token = _make_admin(db_session, username="disabled-admin", permissions=["movies.manage"], active=False)
    assert client.get("/api/admin/movies", headers=_headers(token)).status_code == 401


def test_expired_and_malformed_tokens_rejected(client):
    settings = get_settings()
    expired = jwt.encode(
        {
            "sub": "1",
            "typ": "admin",
            "username": "admin",
            "exp": datetime.now(UTC) - timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    assert client.get("/api/admin/movies", headers=_headers(expired)).status_code == 401
    assert client.get("/api/admin/movies", headers=_headers("not-a-jwt")).status_code == 401


def test_super_admin_from_seed_still_works(client, admin_headers):
    # Seeded admin still uses legacy keys including movies/series/genres.
    assert client.get("/api/admin/movies", headers=admin_headers).status_code == 200
    assert client.get("/api/admin/genres", headers=admin_headers).status_code == 200
    login = client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": TEST_ADMIN_PASSWORD},
    )
    assert login.status_code == 200
