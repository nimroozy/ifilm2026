"""Premium movie detail: credits, trailer selection, similar content."""

from __future__ import annotations

from app.core.config import Settings
from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.collections import Collection, CollectionItem
from app.models.content import Genre, Movie
from app.models.credits import MovieCastCredit
from app.models.media_assets import new_uuid, utcnow
from app.services.tmdb.credits import parse_cast_entries, replace_movie_credits
from app.services.tmdb.trailers import select_trailer
from app.services.similar_content import list_similar_movies


def _settings() -> Settings:
    return Settings(
        app_env="test",
        debug=False,
        jwt_secret="x" * 32,
        database_url="sqlite://",
        redis_required=False,
        tmdb_enabled=True,
        tmdb_api_read_token="test-token",
        tmdb_language="en-US",
        tmdb_image_base_url="https://image.tmdb.org/t/p/",
    )


def _admin(db_session) -> str:
    role = AdminRole(name=f"md-{new_uuid()[:6]}", permissions=["movies.manage", "catalog.edit"])
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username=f"md-admin-{new_uuid()[:6]}",
        email=f"{new_uuid()[:6]}@ex.test",
        full_name="MD Admin",
        hashed_password=hash_password("admin-pass-ok"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    return create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})


def _movie(db_session, *, slug: str, tmdb_id: int | None = None, genres: list[Genre] | None = None) -> Movie:
    movie = Movie(
        title=slug.replace("-", " ").title(),
        slug=slug,
        description="Synopsis",
        release_year=2024,
        poster_url="https://example.test/p.jpg",
        backdrop_url="https://example.test/b.jpg",
        status="published",
        published_at=utcnow(),
        tmdb_id=tmdb_id,
        metadata_source="tmdb" if tmdb_id else "",
        trailer_provider="YouTube",
        trailer_key="abc123XYZ",
        trailer_url="https://www.youtube-nocookie.com/embed/abc123XYZ",
        trailer_official=True,
    )
    if genres:
        movie.genre_links = genres
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def test_select_trailer_youtube_only():
    payload = {
        "results": [
            {"site": "Vimeo", "type": "Trailer", "key": "vimeo1", "official": True},
            {"site": "YouTube", "type": "Teaser", "key": "teaser1", "official": True},
            {
                "site": "YouTube",
                "type": "Trailer",
                "key": "trail1",
                "official": True,
                "iso_639_1": "en",
                "name": "Official Trailer",
            },
        ]
    }
    trailer = select_trailer(payload, language="en-US")
    assert trailer is not None
    assert trailer.key == "trail1"
    assert trailer.provider == "YouTube"
    assert "youtube" in trailer.embed_url


def test_parse_cast_dedupes_and_orders():
    payload = {
        "cast": [
            {"id": 1, "name": "A", "character": "Hero", "order": 1, "profile_path": "/a.jpg"},
            {"id": 1, "name": "A", "character": "Hero again", "order": 0},
            {"id": 2, "name": "B", "character": "Villain", "order": 0, "profile_path": None},
            {"id": 3, "name": "", "character": "X", "order": 2},
        ]
    }
    rows = parse_cast_entries(payload, limit=10)
    # Dedupes person 1 (keeps first sighting), then sorts by credit_order.
    assert [r["tmdb_person_id"] for r in rows] == [2, 1]
    assert rows[1]["character_name"] == "Hero"


def test_replace_movie_credits_persists(db_session):
    movie = _movie(db_session, slug=f"cred-{new_uuid()[:6]}", tmdb_id=101)
    count = replace_movie_credits(
        db_session,
        _settings(),
        movie,
        {
            "cast": [
                {"id": 11, "name": "Actor One", "character": "Lead", "order": 0, "profile_path": "/p.jpg"},
                {"id": 12, "name": "Actor Two", "character": "Support", "order": 1},
            ]
        },
    )
    db_session.commit()
    assert count == 2
    rows = db_session.query(MovieCastCredit).filter_by(movie_id=movie.id).order_by(MovieCastCredit.credit_order).all()
    assert len(rows) == 2
    assert rows[0].name == "Actor One"
    assert movie.cast == ["Actor One", "Actor Two"]
    assert movie.credits_synced_at is not None


def test_public_movie_includes_credits(client, db_session):
    movie = _movie(db_session, slug=f"pub-cred-{new_uuid()[:6]}", tmdb_id=202)
    replace_movie_credits(
        db_session,
        _settings(),
        movie,
        {"cast": [{"id": 5, "name": "Nova", "character": "Pilot", "order": 0, "profile_path": "/n.jpg"}]},
    )
    db_session.commit()
    res = client.get(f"/api/movies/{movie.slug}")
    assert res.status_code == 200
    body = res.json()
    assert body["credits"][0]["name"] == "Nova"
    assert body["credits"][0]["character"] == "Pilot"
    assert body["credits"][0]["person_id"] == 5
    assert "profile_url" in body["credits"][0]


def test_similar_priority_collection_then_genre(db_session):
    g = Genre(name="Action", slug=f"act-{new_uuid()[:6]}")
    db_session.add(g)
    db_session.flush()
    base = _movie(db_session, slug=f"base-{new_uuid()[:6]}", tmdb_id=1, genres=[g])
    coll_peer = _movie(db_session, slug=f"coll-{new_uuid()[:6]}", tmdb_id=2, genres=[g])
    genre_peer = _movie(db_session, slug=f"genre-{new_uuid()[:6]}", tmdb_id=3, genres=[g])
    other = _movie(db_session, slug=f"other-{new_uuid()[:6]}", tmdb_id=4)

    collection = Collection(
        title="Bundle",
        slug=f"bundle-{new_uuid()[:6]}",
        status="published",
        visibility="public",
        published_at=utcnow(),
    )
    db_session.add(collection)
    db_session.flush()
    db_session.add_all(
        [
            CollectionItem(collection_id=collection.id, movie_id=base.id, position=0),
            CollectionItem(collection_id=collection.id, movie_id=coll_peer.id, position=1),
        ]
    )
    db_session.commit()

    similar = list_similar_movies(db_session, base, limit=5)
    ids = [m.id for m in similar]
    assert coll_peer.id in ids
    assert ids.index(coll_peer.id) < ids.index(genre_peer.id)
    assert other.id in ids or genre_peer.id in ids


def test_refresh_title_requires_permission(client, db_session):
    movie = _movie(db_session, slug=f"ref-{new_uuid()[:6]}", tmdb_id=303)
    res = client.post(
        "/api/admin/tools/tmdb/refresh-title",
        json={"media_type": "movie", "entity_id": movie.id},
    )
    assert res.status_code == 401


def test_refresh_title_missing_tmdb(client, db_session):
    movie = _movie(db_session, slug=f"no-tmdb-{new_uuid()[:6]}", tmdb_id=None)
    token = _admin(db_session)
    res = client.post(
        "/api/admin/tools/tmdb/refresh-title",
        headers={"Authorization": f"Bearer {token}"},
        json={"media_type": "movie", "entity_id": movie.id},
    )
    # TMDB disabled/missing token or movie_has_no_tmdb_id
    assert res.status_code in (400, 502)
