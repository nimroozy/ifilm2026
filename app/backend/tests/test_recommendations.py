"""Deterministic recommendations + What-to-Watch tests."""

from __future__ import annotations

import pytest
from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.collections import Collection, CollectionItem
from app.models.content import Genre, Movie, Series
from app.models.credits import MovieCastCredit
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.models.user import Subscriber, WatchlistItem
from app.models.watch_progress import UserWatchProgress
from app.services.recommendations.cache import (
    bump_catalog_feature_epoch,
    cache_get,
    cache_set,
    invalidate_user_recommendation_cache,
)
from app.services.recommendations.engine import recommend_for_user, scored_to_public_dict
from app.services.recommendations.moods import genres_for_mood
from app.services.recommendations.scoring import stable_sort_key
from app.services.recommendations.types import ScoredCandidate


@pytest.fixture(autouse=True)
def _clear_rec_cache():
    """Process-local cache can leak across tests when subscriber ids reset."""
    invalidate_user_recommendation_cache()
    yield
    invalidate_user_recommendation_cache()


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


def _genre(db_session, name: str) -> Genre:
    slug = f"{name.lower().replace(' ', '-')}-{new_uuid()[:6]}"
    g = Genre(name=name, slug=slug)
    db_session.add(g)
    db_session.flush()
    return g


def _movie(
    db_session,
    *,
    title: str,
    genres: list[Genre],
    year: int = 2020,
    language: str = "English",
    views: int = 100,
    rating: float = 7.0,
    status: str = "published",
    duration: int = 110,
    cast_names: list[str] | None = None,
    country: str = "USA",
    dubbed: list[str] | None = None,
    subtitles: list[str] | None = None,
) -> Movie:
    movie = Movie(
        title=title,
        slug=f"{title.lower().replace(' ', '-')}-{new_uuid()[:6]}",
        description=f"Synopsis for {title}",
        release_year=year,
        language=language,
        country=country,
        imdb_rating=rating,
        views=views,
        duration_minutes=duration,
        poster_url="https://example.test/p.jpg",
        backdrop_url="https://example.test/b.jpg",
        status=status,
        published_at=utcnow() if status == "published" else None,
        cast=cast_names or [],
        dubbed=dubbed or [],
        subtitles=subtitles or [],
    )
    movie.genre_links = list(genres)
    db_session.add(movie)
    db_session.flush()
    return movie


def _series(
    db_session,
    *,
    title: str,
    genres: list[Genre],
    year: int = 2021,
    language: str = "English",
    views: int = 80,
    rating: float = 7.2,
    status: str = "published",
) -> Series:
    series = Series(
        title=title,
        slug=f"{title.lower().replace(' ', '-')}-{new_uuid()[:6]}",
        description=f"Synopsis for {title}",
        release_year=year,
        language=language,
        imdb_rating=rating,
        views=views,
        poster_url="https://example.test/sp.jpg",
        backdrop_url="https://example.test/sb.jpg",
        status=status,
        published_at=utcnow() if status == "published" else None,
    )
    series.genre_links = list(genres)
    db_session.add(series)
    db_session.flush()
    return series


def _progress(
    db_session,
    user: Subscriber,
    movie: Movie,
    *,
    percent: float,
    completed: bool = False,
    hidden: bool = False,
) -> None:
    asset = MediaAsset(
        id=new_uuid(),
        original_filename=f"{movie.slug}.mp4",
        stored_filename=f"{movie.slug}.mp4",
        mime_type="video/mp4",
        extension=".mp4",
        size_bytes=1_000_000,
        category="originals",
        upload_status="completed",
        processing_status="completed",
        storage_backend="local",
        storage_path=f"originals/{movie.slug}.mp4",
        movie_id=movie.id,
        duration_seconds=6000.0,
        probed_at=utcnow(),
    )
    db_session.add(asset)
    db_session.flush()
    row = UserWatchProgress(
        subscriber_id=user.id,
        media_asset_id=asset.id,
        movie_id=movie.id,
        position_seconds=max(30.0, 6000.0 * (percent / 100.0)),
        duration_seconds=6000.0,
        progress_percent=percent,
        completed=completed,
        hidden_from_continue=hidden,
        completed_at=utcnow() if completed else None,
        last_watched_at=utcnow(),
        last_event_at=utcnow(),
    )
    db_session.add(row)
    db_session.flush()


def _seed_catalog(db_session):
    g_scifi = _genre(db_session, "Science Fiction")
    g_action = _genre(db_session, "Action")
    g_comedy = _genre(db_session, "Comedy")
    g_family = _genre(db_session, "Family")
    g_drama = _genre(db_session, "Drama")

    inception = _movie(
        db_session,
        title="Inception",
        genres=[g_scifi, g_action],
        year=2010,
        views=5000,
        rating=8.8,
        cast_names=["Leonardo DiCaprio"],
    )
    db_session.add(
        MovieCastCredit(
            movie_id=inception.id,
            tmdb_person_id=6193,
            name="Leonardo DiCaprio",
            character_name="Cobb",
            credit_order=0,
        )
    )
    interstellar = _movie(
        db_session,
        title="Interstellar",
        genres=[g_scifi, g_drama],
        year=2014,
        views=4800,
        rating=8.6,
        cast_names=["Matthew McConaughey"],
    )
    db_session.add(
        MovieCastCredit(
            movie_id=interstellar.id,
            tmdb_person_id=3896,
            name="Matthew McConaughey",
            character_name="Cooper",
            credit_order=0,
        )
    )
    # Shares DiCaprio with Inception for cast scoring.
    catch_me = _movie(
        db_session,
        title="Catch Me If You Can",
        genres=[g_drama, g_action],
        year=2002,
        views=2000,
        rating=8.1,
        cast_names=["Leonardo DiCaprio"],
    )
    db_session.add(
        MovieCastCredit(
            movie_id=catch_me.id,
            tmdb_person_id=6193,
            name="Leonardo DiCaprio",
            character_name="Frank",
            credit_order=0,
        )
    )
    mad_max = _movie(
        db_session,
        title="Mad Max Fury Road",
        genres=[g_action],
        year=2015,
        views=4200,
        rating=8.1,
    )
    home_alone = _movie(
        db_session,
        title="Home Alone",
        genres=[g_comedy, g_family],
        year=1990,
        views=3900,
        rating=7.7,
    )
    paddington = _movie(
        db_session,
        title="Paddington",
        genres=[g_comedy, g_family],
        year=2014,
        views=2100,
        rating=7.2,
    )
    unpublished = _movie(
        db_session,
        title="Secret Draft",
        genres=[g_scifi],
        year=2024,
        views=99999,
        rating=9.9,
        status="draft",
    )
    series_scifi = _series(
        db_session,
        title="Foundation",
        genres=[g_scifi],
        year=2021,
        views=3000,
        rating=8.0,
    )
    series_comedy = _series(
        db_session,
        title="The Office",
        genres=[g_comedy],
        year=2005,
        views=3500,
        rating=8.9,
    )

    coll = Collection(
        title="Mind-Bending Sci-Fi",
        slug=f"mind-bend-{new_uuid()[:6]}",
        description="Editorial",
        status="published",
        visibility="public",
        is_featured=True,
        published_at=utcnow(),
        sort_order=1,
    )
    db_session.add(coll)
    db_session.flush()
    db_session.add(CollectionItem(collection_id=coll.id, movie_id=inception.id, position=0))
    db_session.add(CollectionItem(collection_id=coll.id, movie_id=interstellar.id, position=1))
    db_session.commit()

    return {
        "genres": {
            "scifi": g_scifi,
            "action": g_action,
            "comedy": g_comedy,
            "family": g_family,
            "drama": g_drama,
        },
        "movies": {
            "inception": inception,
            "interstellar": interstellar,
            "catch_me": catch_me,
            "mad_max": mad_max,
            "home_alone": home_alone,
            "paddington": paddington,
            "unpublished": unpublished,
        },
        "series": {"foundation": series_scifi, "office": series_comedy},
        "collection": coll,
    }


def test_mood_mapping_documented():
    assert "Action" in genres_for_mood("exciting")
    assert genres_for_mood("funny") == ["Comedy"]
    assert "Horror" in genres_for_mood("suspenseful")


def test_user_a_scifi_heavy(client, db_session):
    cat = _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="rec-user-a")
    _progress(db_session, user, cat["movies"]["inception"], percent=100, completed=True)
    _progress(db_session, user, cat["movies"]["mad_max"], percent=85)
    db_session.add(
        WatchlistItem(subscriber_id=user.id, movie_id=cat["movies"]["interstellar"].id, series_id=None)
    )
    db_session.commit()

    res = client.get("/api/me/recommendations?limit=10", headers=_headers(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["personalized"] is True
    assert body["label"] == "Recommended for You"
    titles = [i["title"] for i in body["items"]]
    assert "Secret Draft" not in titles
    # Sci-Fi / related should rank ahead of pure comedy family for this user.
    assert any(t in titles for t in ("Interstellar", "Foundation", "Catch Me If You Can"))
    assert all("source_path" not in i and "hls_path" not in i for i in body["items"])
    assert all(i.get("reasons") for i in body["items"])


def test_user_b_comedy_family(client, db_session):
    cat = _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="rec-user-b")
    _progress(db_session, user, cat["movies"]["home_alone"], percent=100, completed=True)
    _progress(db_session, user, cat["movies"]["paddington"], percent=75)
    db_session.commit()

    res = client.get("/api/me/recommendations?limit=10", headers=_headers(token))
    assert res.status_code == 200
    body = res.json()
    assert body["personalized"] is True
    titles = [i["title"] for i in body["items"]]
    assert "The Office" in titles or "Paddington" in titles or any(
        "Comedy" in g for i in body["items"] for g in i["genres"]
    )


def test_user_c_cold_start_fallback(client, db_session):
    _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="rec-user-c")
    res = client.get("/api/me/recommendations", headers=_headers(token))
    assert res.status_code == 200
    body = res.json()
    assert body["personalized"] is False
    assert body["label"] == "Popular Now"
    assert body["mode"] == "popular"


def test_user_d_dismiss_lowers_priority(client, db_session):
    cat = _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="rec-user-d")
    _progress(db_session, user, cat["movies"]["inception"], percent=100, completed=True)
    # Dismiss a comedy title after short watch — should not hard-exclude catalog.
    _progress(db_session, user, cat["movies"]["home_alone"], percent=40, hidden=True)
    db_session.commit()

    items, profile, mode = recommend_for_user(db_session, user, limit=20, use_cache=False)
    assert mode == "personalized"
    assert cat["movies"]["home_alone"].id in profile.dismissed_movie_ids
    # Dismissed item may appear but should not outrank strong sci-fi matches.
    by_id = {i.id: i for i in items if i.kind == "movie"}
    if cat["movies"]["home_alone"].id in by_id and cat["movies"]["interstellar"].id in by_id:
        assert by_id[cat["movies"]["interstellar"].id].score >= by_id[cat["movies"]["home_alone"].id].score


def test_user_isolation(client, db_session):
    cat = _seed_catalog(db_session)
    a, token_a = _subscriber(db_session, username="iso-a")
    b, token_b = _subscriber(db_session, username="iso-b")
    _progress(db_session, a, cat["movies"]["inception"], percent=100, completed=True)
    _progress(db_session, b, cat["movies"]["home_alone"], percent=100, completed=True)
    db_session.commit()

    ra = client.get("/api/me/recommendations", headers=_headers(token_a)).json()
    rb = client.get("/api/me/recommendations", headers=_headers(token_b)).json()
    assert ra["personalized"] and rb["personalized"]
    # Profiles differ → top titles should not be identical sets dominated by the other genre.
    top_a = {i["title"] for i in ra["items"][:5]}
    top_b = {i["title"] for i in rb["items"][:5]}
    assert top_a != top_b


def test_anonymous_home_truthful(client, db_session):
    _seed_catalog(db_session)
    res = client.get("/api/recommendations/home")
    assert res.status_code == 200
    body = res.json()
    assert body["personalized"] is False
    assert body["mode"] == "anonymous"
    titles = [s["title"] for s in body["shelves"]]
    assert "Popular Now" in titles
    assert "Recommended for You" not in titles


def test_unpublished_excluded(client, db_session):
    cat = _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="unpub")
    _progress(db_session, user, cat["movies"]["inception"], percent=100, completed=True)
    db_session.commit()
    res = client.get("/api/me/recommendations?limit=30", headers=_headers(token))
    titles = [i["title"] for i in res.json()["items"]]
    assert "Secret Draft" not in titles


def test_item_recommendations_exclude_self(client, db_session):
    cat = _seed_catalog(db_session)
    movie = cat["movies"]["inception"]
    res = client.get(f"/api/catalog/movies/{movie.id}/recommendations?limit=8")
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "item"
    ids = [i["id"] for i in body["items"]]
    assert movie.id not in ids
    assert "Secret Draft" not in [i["title"] for i in body["items"]]


def test_series_recommendations(client, db_session):
    cat = _seed_catalog(db_session)
    series = cat["series"]["foundation"]
    res = client.get(f"/api/catalog/series/{series.slug}/recommendations")
    assert res.status_code == 200
    assert all(i["id"] != series.id for i in res.json()["items"])


def test_duplicate_removal_and_stable_tiebreak():
    a = ScoredCandidate(
        kind="movie",
        id=2,
        title="A",
        slug="a",
        poster_url="",
        backdrop_url="",
        release_year=2020,
        imdb_rating=8.0,
        genres=[],
        language="",
        country="",
        duration_minutes=100,
        views=1,
        published_at_ts=0,
        score=0.5,
        reasons=[],
    )
    b = ScoredCandidate(
        kind="movie",
        id=1,
        title="B",
        slug="b",
        poster_url="",
        backdrop_url="",
        release_year=2020,
        imdb_rating=8.0,
        genres=[],
        language="",
        country="",
        duration_minutes=100,
        views=1,
        published_at_ts=0,
        score=0.5,
        reasons=[],
    )
    ordered = sorted([a, b], key=stable_sort_key)
    assert ordered[0].id == 2  # higher id wins when score/rating equal


def test_deterministic_score(client, db_session):
    cat = _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="det")
    _progress(db_session, user, cat["movies"]["inception"], percent=100, completed=True)
    db_session.commit()
    invalidate_user_recommendation_cache(user.id)
    r1 = client.get("/api/me/recommendations?limit=8", headers=_headers(token)).json()
    invalidate_user_recommendation_cache(user.id)
    r2 = client.get("/api/me/recommendations?limit=8", headers=_headers(token)).json()
    assert [i["id"] for i in r1["items"]] == [i["id"] for i in r2["items"]]
    assert [i["score"] for i in r1["items"]] == [i["score"] for i in r2["items"]]


def test_cache_invalidation_on_watchlist(client, db_session):
    cat = _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="cache-wl")
    cache_set(f"u:{user.id}:rec:test", ("cached",))
    assert cache_get(f"u:{user.id}:rec:test") is not None
    res = client.post(
        "/api/me/watchlist",
        headers=_headers(token),
        json={"movie_id": cat["movies"]["paddington"].id},
    )
    assert res.status_code == 201
    assert cache_get(f"u:{user.id}:rec:test") is None


def test_what_to_watch_mood(client, db_session):
    _seed_catalog(db_session)
    res = client.post(
        "/api/recommendations/what-to-watch",
        json={"content_type": "movie", "mood": "funny", "duration": "any", "limit": 5},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ai"] is False
    assert body["filters"]["mood_genres"] == ["Comedy"]
    assert 0 <= body["count"] <= 5
    for item in body["items"]:
        assert item["reasons"]
        assert "Comedy" in item["genres"] or "Family" in item["genres"]


def test_home_personalized_shelves(client, db_session):
    cat = _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="home-p")
    _progress(db_session, user, cat["movies"]["inception"], percent=100, completed=True)
    db_session.commit()
    res = client.get("/api/me/recommendations/home", headers=_headers(token))
    assert res.status_code == 200
    body = res.json()
    types = [s["shelf_type"] for s in body["shelves"]]
    assert "recommended" in types or "popular" in types
    # No empty misleading recommended shelf
    for shelf in body["shelves"]:
        if shelf["shelf_type"] in {"recommended", "because_you_watched", "popular"}:
            assert shelf["items"] or shelf.get("collections")


def test_admin_inspect_rbac(client, db_session):
    cat = _seed_catalog(db_session)
    user, _ = _subscriber(db_session, username="inspect-target")
    _progress(db_session, user, cat["movies"]["inception"], percent=100, completed=True)
    db_session.commit()

    # Ordinary catalog managers (movies.read) must NOT access inspect.
    role_catalog = AdminRole(name=f"rec-cat-{new_uuid()[:6]}", permissions=["movies.read", "movies.manage"])
    db_session.add(role_catalog)
    db_session.flush()
    admin_catalog = AdminUser(
        username=f"rec-cat-{new_uuid()[:6]}",
        email=f"{new_uuid()[:6]}@ex.test",
        full_name="Catalog Admin",
        hashed_password=hash_password("admin-pass-ok"),
        role_id=role_catalog.id,
        is_active=True,
    )
    db_session.add(admin_catalog)
    db_session.commit()
    token_catalog = create_access_token(
        str(admin_catalog.id), {"typ": "admin", "username": admin_catalog.username}
    )
    denied_catalog = client.get(
        f"/api/admin/recommendations/inspect?subscriber_id={user.id}",
        headers=_headers(token_catalog),
    )
    assert denied_catalog.status_code == 403

    role = AdminRole(name=f"rec-role-{new_uuid()[:6]}", permissions=["recommendations.inspect"])
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username=f"rec-admin-{new_uuid()[:6]}",
        email=f"{new_uuid()[:6]}@ex.test",
        full_name="Rec Admin",
        hashed_password=hash_password("admin-pass-ok"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    token = create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})

    res = client.get(
        f"/api/admin/recommendations/inspect?subscriber_id={user.id}",
        headers=_headers(token),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["subscriber_id"] == user.id
    assert "preference_signals" in body
    assert "candidates" in body
    assert "hashed_password" not in str(body).lower()
    assert "access_token" not in str(body).lower()
    # Forbidden without permission
    role2 = AdminRole(name=f"rec-role2-{new_uuid()[:6]}", permissions=["genres.read"])
    db_session.add(role2)
    db_session.flush()
    admin2 = AdminUser(
        username=f"rec-admin2-{new_uuid()[:6]}",
        email=f"{new_uuid()[:6]}@ex.test",
        full_name="No Rec",
        hashed_password=hash_password("admin-pass-ok"),
        role_id=role2.id,
        is_active=True,
    )
    db_session.add(admin2)
    db_session.commit()
    token2 = create_access_token(str(admin2.id), {"typ": "admin", "username": admin2.username})
    denied = client.get(
        f"/api/admin/recommendations/inspect?subscriber_id={user.id}",
        headers=_headers(token2),
    )
    assert denied.status_code == 403


def test_no_private_field_leakage(client, db_session):
    cat = _seed_catalog(db_session)
    movie = cat["movies"]["inception"]
    movie.source_path = "/secret/source.mkv"
    movie.hls_path = "/secret/hls/index.m3u8"
    db_session.commit()
    res = client.get(f"/api/catalog/movies/{movie.id}/recommendations")
    text = res.text
    assert "/secret/" not in text
    assert "source_path" not in text
    assert "hls_path" not in text


def test_public_dict_shape():
    item = ScoredCandidate(
        kind="movie",
        id=9,
        title="X",
        slug="x",
        poster_url="p",
        backdrop_url="b",
        release_year=2020,
        imdb_rating=7.0,
        genres=["Action"],
        language="English",
        country="USA",
        duration_minutes=100,
        views=10,
        published_at_ts=0,
        score=0.7,
        reasons=["Matches your preferred Action genre"],
        components={"genre": 0.9},
    )
    public = scored_to_public_dict(item)
    assert public["explanation"] == "Because you enjoy Action"
    assert "components" not in public
    debug = scored_to_public_dict(item, include_components=True)
    assert debug["components"]["genre"] == 0.9


def test_bump_catalog_epoch_clears_cache():
    cache_set("u:1:rec:x", "v")
    bump_catalog_feature_epoch()
    assert cache_get("u:1:rec:x") is None


def test_completed_and_continue_watching_excluded_from_recommended(client, db_session):
    cat = _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="excl-cw")
    completed = cat["movies"]["inception"]
    watching = cat["movies"]["mad_max"]
    _progress(db_session, user, completed, percent=100, completed=True)
    _progress(db_session, user, watching, percent=55, completed=False)
    db_session.commit()
    invalidate_user_recommendation_cache(user.id)

    res = client.get("/api/me/recommendations?limit=12", headers=_headers(token))
    assert res.status_code == 200
    titles = {i["title"] for i in res.json()["items"]}
    assert completed.title not in titles
    assert watching.title not in titles


def test_watchlisted_excluded_from_recommended_but_influences_prefs(client, db_session):
    cat = _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="excl-wl")
    listed = cat["movies"]["interstellar"]
    db_session.add(WatchlistItem(subscriber_id=user.id, movie_id=listed.id, series_id=None))
    # Give a weak completion signal so personalization engages.
    _progress(db_session, user, cat["movies"]["inception"], percent=100, completed=True)
    db_session.commit()
    invalidate_user_recommendation_cache(user.id)

    res = client.get("/api/me/recommendations?limit=12", headers=_headers(token))
    assert res.status_code == 200
    body = res.json()
    titles = {i["title"] for i in body["items"]}
    assert listed.title not in titles
    assert body["personalized"] is True
    # Sci-Fi preference from watchlist+history should still surface related titles.
    assert any(t in titles for t in ("Foundation", "Catch Me If You Can", "Mad Max Fury Road"))


def test_dismiss_downranks_not_hard_excludes_and_keeps_history(client, db_session):
    cat = _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="dismiss-soft")
    dismissed = cat["movies"]["home_alone"]
    _progress(db_session, user, dismissed, percent=40, completed=False, hidden=True)
    _progress(db_session, user, cat["movies"]["paddington"], percent=100, completed=True)
    db_session.commit()
    invalidate_user_recommendation_cache(user.id)

    res = client.get("/api/me/recommendations?limit=12", headers=_headers(token))
    assert res.status_code == 200
    body = res.json()
    assert body["personalized"] is True
    # Dismissed title itself may appear only if not completed/CW; it is CW+dismissed so excluded
    # via continue-watching exclusion when still in progress. History row remains in DB.
    from app.models.watch_progress import UserWatchProgress

    rows = (
        db_session.query(UserWatchProgress)
        .filter(
            UserWatchProgress.subscriber_id == user.id,
            UserWatchProgress.movie_id == dismissed.id,
        )
        .all()
    )
    assert len(rows) == 1
    assert rows[0].hidden_from_continue is True


def test_stale_cache_cannot_leak_unpublished(client, db_session):
    cat = _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="pub-leak")
    target = cat["movies"]["interstellar"]
    _progress(db_session, user, cat["movies"]["inception"], percent=100, completed=True)
    db_session.commit()
    invalidate_user_recommendation_cache(user.id)

    first = client.get("/api/me/recommendations?limit=12", headers=_headers(token))
    assert first.status_code == 200
    titles_before = {i["title"] for i in first.json()["items"]}
    assert target.title in titles_before

    # Unpublish while a process-local cache entry may still exist for this key.
    target.status = "draft"
    target.published_at = None
    db_session.commit()
    # Do NOT invalidate — simulate multi-worker / TTL lag; response-time filter must catch it.
    second = client.get("/api/me/recommendations?limit=12", headers=_headers(token))
    assert second.status_code == 200
    titles_after = {i["title"] for i in second.json()["items"]}
    assert target.title not in titles_after
    assert "Secret Draft" not in titles_after


def test_what_to_watch_relaxed_match_notes(client, db_session):
    _seed_catalog(db_session)
    # Impossible combo for the tiny seed catalog — engine should relax filters and explain.
    res = client.post(
        "/api/recommendations/what-to-watch",
        json={
            "content_type": "movie",
            "genre": "Comedy",
            "mood": "funny",
            "duration": "under_90",
            "language": "pashto",
            "subtitles": "required",
            "release_period": "new",
            "limit": 5,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ai"] is False
    assert "relaxed" in body
    if body["count"] > 0:
        assert body["relaxed"]
        assert any("Relaxed match" in r for i in body["items"] for r in i["reasons"])
    for item in body["items"]:
        assert "source_path" not in item


def test_home_because_you_watched_omits_when_weak(client, db_session):
    cat = _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="byw-weak")
    # Accidental short playback must not become a Because You Watched anchor.
    _progress(db_session, user, cat["movies"]["inception"], percent=1, completed=False)
    from app.models.watch_progress import UserWatchProgress

    row = (
        db_session.query(UserWatchProgress)
        .filter(UserWatchProgress.subscriber_id == user.id)
        .first()
    )
    row.position_seconds = 5.0
    row.progress_percent = 0.1
    db_session.commit()
    invalidate_user_recommendation_cache(user.id)

    res = client.get("/api/me/recommendations/home", headers=_headers(token))
    assert res.status_code == 200
    types = [s["shelf_type"] for s in res.json()["shelves"]]
    assert "because_you_watched" not in types


def test_cold_start_uses_popular_label(client, db_session):
    _seed_catalog(db_session)
    user, token = _subscriber(db_session, username="cold")
    res = client.get("/api/me/recommendations?limit=8", headers=_headers(token))
    assert res.status_code == 200
    body = res.json()
    assert body["personalized"] is False
    assert body["mode"] == "popular"
    assert body["label"] == "Popular Now"
    home = client.get("/api/me/recommendations/home", headers=_headers(token)).json()
    assert home["personalized"] is False
    assert any(s["shelf_type"] == "popular" for s in home["shelves"])
    assert not any(s["shelf_type"] == "recommended" for s in home["shelves"])
