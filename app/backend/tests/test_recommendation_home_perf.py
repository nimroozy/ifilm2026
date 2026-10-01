"""Homepage recommendation SQL bounds (issue #56).

Measured on the shared recommendation seed catalog with two completed titles,
before this fix (current main):

- ``GET /api/recommendations/home``: 15 statements
- ``GET /api/me/recommendations/home`` first call: 92 statements
- same authenticated call again: 64 statements
- profile builds on the authenticated call: 2
- candidate-pool builds on the authenticated call: 3 (user pool + one per seed)

The audited ~68/48/14 figures are lower than current main; the extra statements
are the same repeated profile and per-seed pool work. Bounds below fail on that
baseline and pass after the home payload reuses one profile, one pool, and a
short-lived cache.
"""

from __future__ import annotations

from app.services.recommendations import engine as rec_engine
from app.services.recommendations.cache import (
    cache_get,
    catalog_feature_epoch,
    invalidate_user_recommendation_cache,
)
from sqlalchemy import event
from tests.test_recommendations import _headers, _movie, _progress, _seed_catalog, _subscriber

# Uncached authenticated home was 92 statements before the fix.
AUTH_HOME_UNCACHED_SQL = 48
# Repeat call was 64 statements before the fix (user-list cache only).
AUTH_HOME_CACHED_SQL = 10
# Anonymous home was 15 statements; keep a small ceiling against N+1 growth.
ANON_HOME_SQL = 20


def _count_sql(client, db_session, path: str, headers: dict[str, str] | None = None) -> int:
    engine = db_session.get_bind()
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        statements.append(str(statement))

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        response = client.get(path, headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
    assert response.status_code == 200, response.text
    return len(statements)


def _seed_two_completions(db_session):
    cat = _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="home-sql")
    _progress(db_session, user, cat["movies"]["inception"], percent=100, completed=True)
    _progress(db_session, user, cat["movies"]["paddington"], percent=100, completed=True)
    db_session.commit()
    invalidate_user_recommendation_cache(user.id)
    return cat, user, token


def test_home_sql_statement_counts(client, db_session):
    _cat, _user, token = _seed_two_completions(db_session)
    headers = _headers(token)

    anon = _count_sql(client, db_session, "/api/recommendations/home")
    anon_again = _count_sql(client, db_session, "/api/recommendations/home")
    auth_first = _count_sql(client, db_session, "/api/me/recommendations/home", headers)
    auth_second = _count_sql(client, db_session, "/api/me/recommendations/home", headers)

    assert anon <= ANON_HOME_SQL
    assert anon_again <= AUTH_HOME_CACHED_SQL
    assert auth_first <= AUTH_HOME_UNCACHED_SQL
    assert auth_second <= AUTH_HOME_CACHED_SQL
    assert auth_second < auth_first


def test_home_builds_profile_and_pool_once_per_request(client, db_session, monkeypatch):
    cat, user, token = _seed_two_completions(db_session)
    # Enough similar titles that Recommended for You cannot consume the pool,
    # so a Because You Watched shelf still has candidates after dedupe.
    for index in range(15):
        _movie(
            db_session,
            title=f"Space Extra {index}",
            genres=[cat["genres"]["scifi"]],
            views=1500 + index,
            rating=7.4,
        )
    db_session.commit()
    invalidate_user_recommendation_cache(user.id)
    headers = _headers(token)
    profile_calls = {"n": 0}
    pool_calls = {"n": 0}
    real_profile = rec_engine.build_preference_profile
    real_pool = rec_engine._candidate_pool

    def counted_profile(*args, **kwargs):
        profile_calls["n"] += 1
        return real_profile(*args, **kwargs)

    def counted_pool(*args, **kwargs):
        pool_calls["n"] += 1
        return real_pool(*args, **kwargs)

    monkeypatch.setattr(rec_engine, "build_preference_profile", counted_profile)
    monkeypatch.setattr(rec_engine, "_candidate_pool", counted_pool)

    first = client.get("/api/me/recommendations/home", headers=headers)
    assert first.status_code == 200, first.text
    assert profile_calls["n"] == 1
    assert pool_calls["n"] == 1
    assert any(shelf["shelf_type"] == "because_you_watched" for shelf in first.json()["shelves"])

    profile_calls["n"] = 0
    pool_calls["n"] = 0
    second = client.get("/api/me/recommendations/home", headers=headers)
    assert second.status_code == 200, second.text
    assert profile_calls["n"] == 0
    assert pool_calls["n"] == 0
    assert [shelf["shelf_type"] for shelf in first.json()["shelves"]] == [
        shelf["shelf_type"] for shelf in second.json()["shelves"]
    ]


def test_home_cache_invalidated_when_watchlist_changes(client, db_session):
    cat, user, token = _seed_two_completions(db_session)
    headers = _headers(token)
    listed = cat["movies"]["interstellar"]

    first = client.get("/api/me/recommendations/home", headers=headers)
    assert first.status_code == 200, first.text
    cache_key = f"u:{user.id}:home:{catalog_feature_epoch()}"
    assert cache_get(cache_key) is not None

    saved = client.post("/api/me/watchlist", headers=headers, json={"movie_id": listed.id})
    assert saved.status_code == 201, saved.text
    assert cache_get(cache_key) is None

    second = client.get("/api/me/recommendations/home", headers=headers)
    assert second.status_code == 200, second.text
    titles = {
        item["title"]
        for shelf in second.json()["shelves"]
        for item in shelf.get("items") or []
    }
    assert listed.title not in titles


def test_home_cache_does_not_leak_unpublished_titles(client, db_session):
    cat, _user, token = _seed_two_completions(db_session)
    headers = _headers(token)
    target = cat["movies"]["interstellar"]

    first = client.get("/api/me/recommendations/home", headers=headers)
    assert first.status_code == 200, first.text
    def _movie_ids(payload: dict) -> set[int]:
        return {
            int(item["id"])
            for shelf in payload["shelves"]
            for item in shelf.get("items") or []
            if item.get("content_type") == "movie"
        }

    assert target.id in _movie_ids(first.json())

    target.status = "draft"
    target.published_at = None
    db_session.commit()

    second = client.get("/api/me/recommendations/home", headers=headers)
    assert second.status_code == 200, second.text
    assert target.id not in _movie_ids(second.json())
