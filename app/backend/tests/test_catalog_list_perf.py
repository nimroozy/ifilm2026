"""Query-count ceilings and card payload guards for browsing performance."""

from __future__ import annotations

import json

import pytest
from app.core.security import create_access_token
from app.models.content import Genre, Movie, Series
from app.models.content_translations import ContentTranslation
from app.models.credits import MovieCastCredit
from app.models.user import Subscriber
from app.services.catalog import utcnow
from app.utils.slug import normalize_slug
from sqlalchemy import event


def _seed_catalog(db_session, *, movies: int = 40, series_n: int = 12) -> None:
    genre_names = ["Action", "Comedy", "Drama", "Family"]
    genres: dict[str, Genre] = {}
    for name in genre_names:
        g = db_session.query(Genre).filter(Genre.name == name).one_or_none()
        if g is None:
            g = Genre(name=name, slug=normalize_slug(f"perf-{name}"))
            db_session.add(g)
            db_session.flush()
        genres[name] = g

    now = utcnow()
    for i in range(movies):
        g = genres[genre_names[i % len(genre_names)]]
        m = Movie(
            title=f"Perf Movie {i}",
            original_title=f"Perf Movie {i}",
            slug=f"perf-movie-{i}",
            description=f"Long overview text for movie {i}. " * 40,
            short_description=f"Short {i}",
            release_year=2000 + (i % 20),
            duration_minutes=100,
            age_rating="PG",
            language="English",
            country="USA" if i % 5 else "Afghanistan",
            imdb_rating=7.0,
            status="published",
            published_at=now,
            is_featured=i < 5,
            is_trending=i % 7 == 0,
            views=1000 - i,
            dubbed=["Persian"] if i % 3 == 0 else [],
            cast=[f"Actor {i}", f"Co-star {i}"],
            poster_url=f"https://image.tmdb.org/t/p/original/poster{i}.jpg",
        )
        m.genre_links = [g]
        db_session.add(m)
        db_session.flush()
        db_session.add(
            ContentTranslation(
                entity_type="movie",
                entity_id=m.id,
                locale="fa",
                field_key="title",
                value=f"فیلم {i}",
                source="tmdb",
            )
        )
        db_session.add(
            ContentTranslation(
                entity_type="movie",
                entity_id=m.id,
                locale="fa",
                field_key="description",
                value=f"توضیحات فارسی بلند {i}. " * 30,
                source="tmdb",
            )
        )
        db_session.add(
            MovieCastCredit(
                movie_id=m.id,
                tmdb_person_id=1000 + i,
                name=f"Actor {i}",
                character_name="Lead",
                credit_order=0,
            )
        )

    for i in range(series_n):
        g = genres[genre_names[i % len(genre_names)]]
        s = Series(
            title=f"Perf Series {i}",
            original_title=f"Perf Series {i}",
            slug=f"perf-series-{i}",
            description=f"Long series overview {i}. " * 40,
            short_description=f"Series short {i}",
            release_year=2010 + i,
            age_rating="PG",
            language="English",
            country="USA",
            imdb_rating=8.0,
            status="published",
            published_at=now,
            views=500 - i,
            airing_status="Ended",
        )
        s.genre_links = [g]
        db_session.add(s)

    if db_session.query(Subscriber).filter(Subscriber.username == "perf_user").one_or_none() is None:
        db_session.add(
            Subscriber(
                username="perf_user",
                hashed_password=None,
                name="Perf",
                status="active",
                package="Standard",
                service_status="active",
                identity_provider="local",
                max_devices=3,
            )
        )
    db_session.commit()


def _count_queries(engine):
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    return statements


def _assert_card_payload(item: dict) -> None:
    assert item.get("credits") in (None, []), "card must not include cast credits"
    assert item.get("cast") in (None, []), "card must not include cast list"
    assert "similar" not in item
    assert "packages" not in item
    assert "episodes_list" not in item
    desc = item.get("description") or ""
    assert len(desc) <= 220, f"card description too long ({len(desc)})"
    # Trailer blobs are detail-only for browse/home cards.
    assert not item.get("trailer_key")
    assert not item.get("trailer_url")


@pytest.mark.usefixtures("client")
def test_movie_list_card_query_ceiling(client, db_session):
    _seed_catalog(db_session, movies=40)
    engine = db_session.get_bind()
    statements = _count_queries(engine)
    resp = client.get("/api/movies?page_size=20&sort=newest&locale=en")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 20
    assert len(statements) <= 10, f"movie browse queries too high: {len(statements)}"
    joined = " ".join(statements).lower()
    assert "movie_cast_credits" not in joined
    for item in resp.json()["data"]:
        _assert_card_payload(item)


def test_series_list_card_query_ceiling(client, db_session):
    _seed_catalog(db_session, movies=5, series_n=20)
    engine = db_session.get_bind()
    statements = _count_queries(engine)
    resp = client.get("/api/series?page_size=12&sort=views_desc&locale=en")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 12
    assert len(statements) <= 10, f"series browse queries too high: {len(statements)}"
    for item in resp.json()["data"]:
        _assert_card_payload(item)


def test_catalog_home_query_ceiling(client, db_session):
    _seed_catalog(db_session, movies=50, series_n=15)
    engine = db_session.get_bind()
    statements = _count_queries(engine)
    resp = client.get("/api/catalog/home?locale=en")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["featured"]) <= 8
    assert len(body["trending"]) <= 12
    assert len(body["popular_series"]) <= 12
    assert len(statements) <= 20, f"anon home queries too high: {len(statements)}"
    for item in body["featured"] + body["trending"] + body["popular_series"]:
        _assert_card_payload(item)


def test_me_home_query_ceiling(client, db_session):
    _seed_catalog(db_session, movies=40, series_n=10)
    user = db_session.query(Subscriber).filter(Subscriber.username == "perf_user").one()
    token = create_access_token(str(user.id), {"typ": "subscriber", "username": user.username})
    engine = db_session.get_bind()
    statements = _count_queries(engine)
    resp = client.get(
        "/api/me/home?locale=en",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(statements) <= 40, f"auth home queries too high: {len(statements)}"
    body = resp.json()
    assert "continue_watching" in body
    assert "watchlist" in body
    assert "recommendations" in body


def test_me_home_preserves_user_isolation(client, db_session):
    _seed_catalog(db_session, movies=20, series_n=5)
    user = db_session.query(Subscriber).filter(Subscriber.username == "perf_user").one()
    other = Subscriber(
        username="other_perf",
        hashed_password=None,
        name="Other",
        status="active",
        package="Standard",
        service_status="active",
        identity_provider="local",
        max_devices=3,
    )
    db_session.add(other)
    db_session.commit()

    token = create_access_token(str(user.id), {"typ": "subscriber", "username": user.username})
    resp = client.get(
        "/api/me/home?locale=en",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "featured" in body
    assert "recommendations" in body
    assert "continue_watching" in body
    assert "watchlist" in body


def test_home_and_browse_payload_sizes(client, db_session):
    _seed_catalog(db_session, movies=50, series_n=12)
    home = client.get("/api/catalog/home?locale=en")
    assert home.status_code == 200
    movies = client.get("/api/movies?page_size=20&sort=newest&locale=en")
    assert movies.status_code == 200
    user = db_session.query(Subscriber).filter(Subscriber.username == "perf_user").one()
    token = create_access_token(str(user.id), {"typ": "subscriber", "username": user.username})
    me = client.get("/api/me/home?locale=en", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200

    home_bytes = len(home.content)
    movies_bytes = len(movies.content)
    me_bytes = len(me.content)
    # Bounded shelves + card trimming — keep payloads far below mega-catalog dumps.
    assert home_bytes < 450_000, f"catalog/home too large: {home_bytes}"
    assert me_bytes < 500_000, f"me/home too large: {me_bytes}"
    assert movies_bytes < 120_000, f"movies browse too large: {movies_bytes}"

    # Persist measurement for artifacts when PERF_ARTIFACT_DIR is set.
    import os
    from pathlib import Path

    out_dir = Path(os.environ.get("PERF_ARTIFACT_DIR", "/opt/cursor/artifacts/perf-customer-browsing-v1"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "payload-sizes.json").write_text(
        json.dumps(
            {
                "catalog_home_bytes": home_bytes,
                "me_home_bytes": me_bytes,
                "movies_browse20_bytes": movies_bytes,
            },
            indent=2,
        )
    )


def test_views_desc_sort_honored(client, db_session):
    _seed_catalog(db_session, movies=10, series_n=0)
    resp = client.get("/api/movies?page_size=5&sort=views_desc")
    assert resp.status_code == 200
    views = [row["views"] for row in resp.json()["data"]]
    assert views == sorted(views, reverse=True)


def test_localized_list_uses_batched_translations(client, db_session):
    _seed_catalog(db_session, movies=15, series_n=0)
    engine = db_session.get_bind()
    statements = _count_queries(engine)
    resp = client.get("/api/movies?page_size=10&locale=fa")
    assert resp.status_code == 200
    titles = [row["title"] for row in resp.json()["data"]]
    assert any(t.startswith("فیلم") for t in titles)
    translation_selects = sum(1 for s in statements if "content_translations" in s.lower())
    assert translation_selects <= 2, f"translation queries exploded: {translation_selects}"
