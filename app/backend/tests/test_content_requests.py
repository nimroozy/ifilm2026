"""Content Requests V1: subscriber workflow, duplicates, RBAC, admin transitions."""

from __future__ import annotations

import pytest
from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.content import Movie, Series
from app.models.media_assets import new_uuid, utcnow
from app.models.user import Subscriber
from app.services.content_requests import content_request_rate_limiter


@pytest.fixture(autouse=True)
def _clear_rate_limiter():
    content_request_rate_limiter.clear()
    yield
    content_request_rate_limiter.clear()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _subscriber(db_session, *, username: str) -> tuple[Subscriber, str]:
    user = Subscriber(
        username=username,
        hashed_password=None,
        name=username,
        status="active",
        package="Standard",
        service_status="active",
        identity_provider="local",
        max_devices=3,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(str(user.id), {"typ": "subscriber", "username": user.username})
    return user, token


def _admin(db_session, *, permissions: list[str], username: str | None = None) -> tuple[AdminUser, str]:
    role = AdminRole(name=f"cr-role-{new_uuid()[:6]}", permissions=permissions)
    db_session.add(role)
    db_session.flush()
    uname = username or f"cr-admin-{new_uuid()[:6]}"
    admin = AdminUser(
        username=uname,
        email=f"{uname}@test.local",
        full_name="CR Admin",
        hashed_password=hash_password("test-pass-123"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    token = create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})
    return admin, token


def _movie(db_session, *, title: str, year: int = 2010, tmdb_id: int | None = None, imdb_id: str | None = None) -> Movie:
    movie = Movie(
        title=title,
        slug=f"{title.lower().replace(' ', '-')}-{new_uuid()[:6]}",
        description=f"Synopsis for {title}",
        release_year=year,
        language="English",
        country="USA",
        imdb_rating=8.0,
        views=100,
        duration_minutes=120,
        poster_url="https://example.test/p.jpg",
        backdrop_url="https://example.test/b.jpg",
        status="published",
        published_at=utcnow(),
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def _series(db_session, *, title: str, year: int = 2015, tmdb_id: int | None = None, imdb_id: str | None = None) -> Series:
    series = Series(
        title=title,
        slug=f"{title.lower().replace(' ', '-')}-{new_uuid()[:6]}",
        description=f"Synopsis for {title}",
        release_year=year,
        language="English",
        country="USA",
        imdb_rating=8.0,
        views=100,
        poster_url="https://example.test/p.jpg",
        backdrop_url="https://example.test/b.jpg",
        status="published",
        published_at=utcnow(),
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
    )
    db_session.add(series)
    db_session.commit()
    db_session.refresh(series)
    return series


def test_create_movie_and_series_request(client, db_session):
    _user, token = _subscriber(db_session, username="cr-user-1")
    movie_resp = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "Dune Part Three", "year": 2026},
    )
    assert movie_resp.status_code == 200, movie_resp.text
    body = movie_resp.json()
    assert body["outcome"] == "created"
    assert body["request"]["request_type"] == "movie"
    assert body["request"]["status"] == "new"
    assert "admin_note" not in body["request"]

    series_resp = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "series", "title": "Foundation S4", "year": 2027},
    )
    assert series_resp.status_code == 200
    assert series_resp.json()["outcome"] == "created"
    assert series_resp.json()["request"]["request_type"] == "series"


def test_user_isolation_and_idor(client, db_session):
    _a, token_a = _subscriber(db_session, username="cr-a")
    _b, token_b = _subscriber(db_session, username="cr-b")
    created = client.post(
        "/api/me/content-requests",
        headers=_headers(token_a),
        json={"request_type": "movie", "title": "Private Request Alpha"},
    ).json()
    req_id = created["request"]["id"]

    assert client.get(f"/api/me/content-requests/{req_id}", headers=_headers(token_b)).status_code == 404
    assert client.delete(f"/api/me/content-requests/{req_id}", headers=_headers(token_b)).status_code == 404
    listed = client.get("/api/me/content-requests", headers=_headers(token_b)).json()
    items = listed["data"] if isinstance(listed, dict) and "data" in listed else listed
    assert all(item["id"] != req_id for item in items)


def test_exact_catalog_duplicate_blocks_create(client, db_session):
    movie = _movie(db_session, title="Inception", year=2010, tmdb_id=27205, imdb_id="tt1375666")
    _user, token = _subscriber(db_session, username="cr-dup-cat")
    resp = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={
            "request_type": "movie",
            "title": "Something Else",
            "tmdb_url": "https://www.themoviedb.org/movie/27205",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["outcome"] == "already_available"
    assert body["catalog_item"]["id"] == movie.id
    assert body["request"] is None


def test_duplicate_tmdb_imdb_and_title_year(client, db_session):
    _user, token = _subscriber(db_session, username="cr-dup-user")
    first = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={
            "request_type": "movie",
            "title": "Oppenheimer",
            "year": 2023,
            "tmdb_id": 872585,
            "imdb_id": "tt15398776",
        },
    )
    assert first.status_code == 200
    assert first.json()["outcome"] == "created"
    rid = first.json()["request"]["id"]

    by_tmdb = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "Oppy", "tmdb_id": 872585},
    ).json()
    assert by_tmdb["outcome"] == "existing_request"
    assert by_tmdb["request"]["id"] == rid

    by_imdb = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "Oppy 2", "imdb_id": "tt15398776"},
    ).json()
    assert by_imdb["outcome"] == "existing_request"

    by_title = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "Oppenheimer!", "year": 2023},
    ).json()
    assert by_title["outcome"] == "existing_request"


def test_multiple_users_same_title_aggregate_demand(client, db_session):
    _a, token_a = _subscriber(db_session, username="cr-dem-a")
    _b, token_b = _subscriber(db_session, username="cr-dem-b")
    for token in (token_a, token_b):
        resp = client.post(
            "/api/me/content-requests",
            headers=_headers(token),
            json={"request_type": "movie", "title": "Dune: Part Three", "year": 2026},
        )
        assert resp.json()["outcome"] == "created"

    admin, admin_token = _admin(
        db_session, permissions=["content_requests.read", "content_requests.manage"]
    )
    _ = admin
    listed = client.get("/api/admin/content-requests", headers=_headers(admin_token)).json()
    assert listed["total"] >= 2
    agg = next(a for a in listed["aggregates"] if a["normalized_title"] == "dune part three")
    assert agg["request_count"] >= 2

    # Subscriber list must not leak other identities
    mine = client.get("/api/me/content-requests", headers=_headers(token_a)).json()
    data = mine["data"]
    assert len(data) == 1
    assert "subscriber_username" not in data[0]
    assert "admin_note" not in data[0]
    assert data[0]["demand_count"] >= 2


def test_rate_limit_per_day(client, db_session, monkeypatch):
    from app.core.config import get_settings
    from app.services import content_requests as cr_service

    monkeypatch.setenv("CONTENT_REQUEST_MAX_PER_DAY", "2")
    get_settings.cache_clear()
    try:
        _user, token = _subscriber(db_session, username="cr-rate")
        for i in range(2):
            assert (
                client.post(
                    "/api/me/content-requests",
                    headers=_headers(token),
                    json={"request_type": "movie", "title": f"Rate Limit Film {i}"},
                ).status_code
                == 200
            )
        limited = client.post(
            "/api/me/content-requests",
            headers=_headers(token),
            json={"request_type": "movie", "title": "Rate Limit Film Overflow"},
        )
        assert limited.status_code == 429
        assert limited.json()["detail"]["code"] == "rate_limited"
    finally:
        monkeypatch.delenv("CONTENT_REQUEST_MAX_PER_DAY", raising=False)
        get_settings.cache_clear()
        cr_service.content_request_rate_limiter.clear()


def test_status_transitions_link_and_illegal(client, db_session):
    _user, token = _subscriber(db_session, username="cr-flow")
    created = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "Arrival Sequel"},
    ).json()["request"]
    rid = created["id"]
    movie = _movie(db_session, title="Arrival Sequel Catalog", year=2028)

    admin, admin_token = _admin(
        db_session, permissions=["content_requests.read", "content_requests.manage"]
    )
    _ = admin

    assert (
        client.post(
            f"/api/admin/content-requests/{rid}/actions",
            headers=_headers(admin_token),
            json={"action": "review"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/admin/content-requests/{rid}/actions",
            headers=_headers(admin_token),
            json={"action": "approve", "public_response": "Queued for import"},
        ).json()["status"]
        == "approved"
    )
    # Illegal: rejected → added without reopen is tested via reject path below
    added = client.post(
        f"/api/admin/content-requests/{rid}/actions",
        headers=_headers(admin_token),
        json={"action": "mark_added", "linked_movie_id": movie.id},
    )
    assert added.status_code == 200
    assert added.json()["status"] == "added"
    assert added.json()["linked_movie_id"] == movie.id
    assert added.json()["public_response"] == "Available now"

    sub = client.get(f"/api/me/content-requests/{rid}", headers=_headers(token)).json()
    assert sub["status"] == "added"
    assert sub["linked_detail_path"] == f"/movie/{movie.slug}"
    assert "admin_note" not in sub

    # New request to test reject → added illegal
    created2 = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "series", "title": "Rejected Show"},
    ).json()["request"]["id"]
    client.post(
        f"/api/admin/content-requests/{created2}/actions",
        headers=_headers(admin_token),
        json={"action": "reject", "admin_note": "private reason"},
    )
    illegal = client.post(
        f"/api/admin/content-requests/{created2}/actions",
        headers=_headers(admin_token),
        json={"action": "mark_added", "linked_series_id": 1},
    )
    assert illegal.status_code == 409

    detail = client.get(f"/api/admin/content-requests/{created2}", headers=_headers(admin_token)).json()
    assert detail["request"]["admin_note"] == "private reason"
    assert detail["events"]


def test_link_series_and_withdraw(client, db_session):
    _user, token = _subscriber(db_session, username="cr-series")
    series = _series(db_session, title="Andor Season 3", year=2026)
    created = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "series", "title": "Andor S3 Request"},
    ).json()["request"]
    rid = created["id"]

    withdrawn = client.delete(f"/api/me/content-requests/{rid}", headers=_headers(token))
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "withdrawn"

    # Cannot withdraw again
    assert client.delete(f"/api/me/content-requests/{rid}", headers=_headers(token)).status_code == 409

    created2 = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "series", "title": "Andor S3 Again", "force": True},
    ).json()["request"]["id"]
    admin, admin_token = _admin(
        db_session, permissions=["content_requests.read", "content_requests.manage"]
    )
    _ = admin
    client.post(
        f"/api/admin/content-requests/{created2}/actions",
        headers=_headers(admin_token),
        json={"action": "approve"},
    )
    linked = client.post(
        f"/api/admin/content-requests/{created2}/actions",
        headers=_headers(admin_token),
        json={"action": "mark_added", "linked_series_id": series.id},
    )
    assert linked.status_code == 200
    assert linked.json()["linked_series_id"] == series.id


def test_rbac_collection_only_denied(client, db_session):
    _user, token = _subscriber(db_session, username="cr-rbac-sub")
    created = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "RBAC Title"},
    ).json()["request"]["id"]

    _collections_admin, collections_token = _admin(
        db_session, permissions=["collections.read", "collections.manage"]
    )
    assert (
        client.get("/api/admin/content-requests", headers=_headers(collections_token)).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/admin/content-requests/{created}/actions",
            headers=_headers(collections_token),
            json={"action": "review"},
        ).status_code
        == 403
    )

    _reader, reader_token = _admin(db_session, permissions=["content_requests.read"])
    assert client.get("/api/admin/content-requests", headers=_headers(reader_token)).status_code == 200
    assert (
        client.post(
            f"/api/admin/content-requests/{created}/actions",
            headers=_headers(reader_token),
            json={"action": "review"},
        ).status_code
        == 403
    )


def test_rbac_role_matrix_catalog_reviewer_super(client, db_session):
    """Catalog Manager manage, Reviewer read-only, Super Admin manage after bootstrap merge."""
    from app.bootstrap import SUPER_PERMISSIONS, ensure_super_admin_permissions
    from app.services.demo.constants import ADMIN_FIXTURES

    _user, token = _subscriber(db_session, username="cr-rbac-matrix")
    created = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "RBAC Matrix Film"},
    ).json()["request"]["id"]

    demo_by_role = {a["role_name"]: a["permissions"] for a in ADMIN_FIXTURES}
    _cm, cm_token = _admin(
        db_session,
        permissions=list(demo_by_role["Catalog Manager"]),
        username="cr-catalog-manager",
    )
    _rev, rev_token = _admin(
        db_session,
        permissions=list(demo_by_role["Reviewer"]),
        username="cr-reviewer",
    )

    # Super Admin role repaired by startup helper
    ensure_super_admin_permissions(db_session)
    db_session.commit()
    _sa, sa_token = _admin(
        db_session, permissions=list(SUPER_PERMISSIONS), username="cr-super-admin"
    )

    assert client.get("/api/admin/content-requests", headers=_headers(cm_token)).status_code == 200
    assert (
        client.post(
            f"/api/admin/content-requests/{created}/actions",
            headers=_headers(cm_token),
            json={"action": "review"},
        ).status_code
        == 200
    )

    assert client.get("/api/admin/content-requests", headers=_headers(rev_token)).status_code == 200
    assert (
        client.post(
            f"/api/admin/content-requests/{created}/actions",
            headers=_headers(rev_token),
            json={"action": "approve"},
        ).status_code
        == 403
    )

    assert client.get("/api/admin/content-requests", headers=_headers(sa_token)).status_code == 200
    assert (
        client.post(
            f"/api/admin/content-requests/{created}/actions",
            headers=_headers(sa_token),
            json={"action": "approve"},
        ).status_code
        == 200
    )


def test_url_validation_rejects_bad_hosts(client, db_session):
    _user, token = _subscriber(db_session, username="cr-url")
    bad = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={
            "request_type": "movie",
            "title": "Evil URL",
            "tmdb_url": "https://evil.example/movie/1",
        },
    )
    assert bad.status_code == 422

    good = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={
            "request_type": "movie",
            "title": "Good URL Film",
            "imdb_url": "https://www.imdb.com/title/tt0111161/",
        },
    )
    assert good.status_code == 200
    assert good.json()["request"]["imdb_id"] == "tt0111161"


def test_fuzzy_suggestions_allow_force(client, db_session):
    _movie(db_session, title="The Matrix Reloaded", year=2003)
    _user, token = _subscriber(db_session, username="cr-fuzzy")
    suggested = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "Matrix"},
    ).json()
    assert suggested["outcome"] == "suggestions"
    assert suggested["suggestions"]

    forced = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "Matrix", "force": True},
    ).json()
    assert forced["outcome"] == "created"


def test_no_admin_note_leakage_on_list(client, db_session):
    _user, token = _subscriber(db_session, username="cr-note")
    rid = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "Note Leak Check"},
    ).json()["request"]["id"]
    admin, admin_token = _admin(
        db_session, permissions=["content_requests.read", "content_requests.manage"]
    )
    _ = admin
    client.post(
        f"/api/admin/content-requests/{rid}/actions",
        headers=_headers(admin_token),
        json={"action": "reject", "admin_note": "SECRET_ADMIN_NOTE", "public_response": "Not planned"},
    )
    listed = client.get("/api/me/content-requests", headers=_headers(token)).json()["data"][0]
    assert listed["public_response"] == "Not planned"
    assert "admin_note" not in listed
    assert "SECRET_ADMIN_NOTE" not in str(listed)


def test_exact_catalog_imdb_and_title_year(client, db_session):
    movie = _movie(db_session, title="Interstellar", year=2014, tmdb_id=157336, imdb_id="tt0816692")
    _user, token = _subscriber(db_session, username="cr-exact-imdb")

    by_imdb = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={
            "request_type": "movie",
            "title": "Different Title",
            "imdb_url": "https://www.imdb.com/title/tt0816692/",
        },
    ).json()
    assert by_imdb["outcome"] == "already_available"
    assert by_imdb["catalog_item"]["id"] == movie.id

    by_title = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "Interstellar", "year": 2014},
    ).json()
    assert by_title["outcome"] == "already_available"

    # Different year must not false-exact-match
    different_year = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "Interstellar", "year": 2015, "force": True},
    ).json()
    assert different_year["outcome"] == "created"


def test_open_request_limit(client, db_session, monkeypatch):
    from app.core.config import get_settings
    from app.services import content_requests as cr_service

    monkeypatch.setenv("CONTENT_REQUEST_MAX_OPEN", "2")
    monkeypatch.setenv("CONTENT_REQUEST_MAX_PER_DAY", "50")
    get_settings.cache_clear()
    try:
        _user, token = _subscriber(db_session, username="cr-open-cap")
        for i in range(2):
            assert (
                client.post(
                    "/api/me/content-requests",
                    headers=_headers(token),
                    json={"request_type": "movie", "title": f"Open Cap {i}", "force": True},
                ).status_code
                == 200
            )
        limited = client.post(
            "/api/me/content-requests",
            headers=_headers(token),
            json={"request_type": "movie", "title": "Open Cap Overflow", "force": True},
        )
        assert limited.status_code == 429
        assert limited.json()["detail"]["code"] == "too_many_open_requests"
        # No partial create
        listed = client.get("/api/me/content-requests", headers=_headers(token)).json()["data"]
        assert len(listed) == 2
    finally:
        monkeypatch.delenv("CONTENT_REQUEST_MAX_OPEN", raising=False)
        monkeypatch.delenv("CONTENT_REQUEST_MAX_PER_DAY", raising=False)
        get_settings.cache_clear()
        cr_service.content_request_rate_limiter.clear()


def test_reopen_and_wrong_type_link(client, db_session):
    _user, token = _subscriber(db_session, username="cr-reopen")
    movie = _movie(db_session, title="Link Target Movie", year=2024)
    series = _series(db_session, title="Link Target Series", year=2024)
    rid = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "Reopen Candidate", "force": True},
    ).json()["request"]["id"]
    admin, admin_token = _admin(
        db_session, permissions=["content_requests.read", "content_requests.manage"]
    )
    _ = admin

    assert (
        client.post(
            f"/api/admin/content-requests/{rid}/actions",
            headers=_headers(admin_token),
            json={"action": "reject", "public_response": "Later"},
        ).json()["status"]
        == "rejected"
    )
    reopened = client.post(
        f"/api/admin/content-requests/{rid}/actions",
        headers=_headers(admin_token),
        json={"action": "reopen"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "reviewing"

    detail = client.get(f"/api/admin/content-requests/{rid}", headers=_headers(admin_token)).json()
    assert any(e["event_type"] for e in detail["events"])
    assert detail["request"]["reviewed_by_admin_id"] == admin.id
    assert detail["request"]["reviewed_at"]

    assert (
        client.post(
            f"/api/admin/content-requests/{rid}/actions",
            headers=_headers(admin_token),
            json={"action": "approve"},
        ).json()["status"]
        == "approved"
    )

    # Movie request cannot link a series (type mismatch → 422)
    wrong = client.post(
        f"/api/admin/content-requests/{rid}/actions",
        headers=_headers(admin_token),
        json={"action": "mark_added", "linked_series_id": series.id},
    )
    assert wrong.status_code == 422

    ok = client.post(
        f"/api/admin/content-requests/{rid}/actions",
        headers=_headers(admin_token),
        json={"action": "mark_added", "linked_movie_id": movie.id},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "added"

    # Cannot withdraw added
    assert client.delete(f"/api/me/content-requests/{rid}", headers=_headers(token)).status_code == 409


def test_withdraw_reviewing_and_optional_fields(client, db_session):
    _user, token = _subscriber(db_session, username="cr-optional")
    created = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={
            "request_type": "movie",
            "title": "Optional Fields Film",
            "year": 2025,
            "preferred_language": "Dari",
            "notes": "Please add Dari subtitles",
            "tmdb_url": "https://www.themoviedb.org/movie/999001",
            "force": True,
        },
    )
    assert created.status_code == 200
    body = created.json()["request"]
    assert body["preferred_language"] == "Dari"
    assert body["notes"] == "Please add Dari subtitles"
    assert body["tmdb_id"] == 999001
    rid = body["id"]

    admin, admin_token = _admin(
        db_session, permissions=["content_requests.read", "content_requests.manage"]
    )
    _ = admin
    client.post(
        f"/api/admin/content-requests/{rid}/actions",
        headers=_headers(admin_token),
        json={"action": "review"},
    )
    withdrawn = client.delete(f"/api/me/content-requests/{rid}", headers=_headers(token))
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "withdrawn"

    # Title required
    missing = client.post(
        "/api/me/content-requests",
        headers=_headers(token),
        json={"request_type": "movie", "title": "   "},
    )
    assert missing.status_code == 422
