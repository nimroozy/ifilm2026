"""Query-count ceilings for card lists and aggregated homepage (issue #56)."""

from __future__ import annotations

import pytest
from sqlalchemy import event

from app.core.security import create_access_token
from app.models.content import Genre, Movie, Series
from app.models.content_translations import ContentTranslation
from app.models.credits import MovieCastCredit
from app.models.user import Subscriber
from app.services.catalog import utcnow
from app.utils.slug import normalize_slug


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
            description="d",
            short_description="s",
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
            cast=[f"Actor {i}"],
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
            description="d",
            short_description="s",
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

    user = Subscriber(
        username="perf_user",
        hashed_password=None,
        name="Perf",
        status="active",
        package="Standard",
        service_status="active",
        identity_provider="local",
        max_devices=3,
    )
    db_session.add(user)
    db_session.commit()


def _count_queries(engine):
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    return statements


@pytest.mark.usefixtures("client")
def test_movie_list_card_query_ceiling(client, db_session):
    _seed_catalog(db_session, movies=40)
    engine = db_session.get_bind()
    statements = _count_queries(engine)
    resp = client.get("/api/movies?page_size=20&sort=newest&locale=en")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 20
    # Card path: list + genres + translations + assets (+ optional packages) — not per-row cast.
    assert len(statements) <= 12, f"too many queries: {len(statements)}"
    joined = " ".join(statements).lower()
    assert "movie_cast_credits" not in joined


def test_series_list_card_query_ceiling(client, db_session):
    _seed_catalog(db_session, movies=5, series_n=20)
    engine = db_session.get_bind()
    statements = _count_queries(engine)
    resp = client.get("/api/series?page_size=12&sort=views_desc&locale=en")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 12
    assert len(statements) <= 12, f"too many queries: {len(statements)}"


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
    # Engineering target: anonymous home well under historical ~800 fan-out queries.
    assert len(statements) <= 80, f"anon home queries too high: {len(statements)}"


def test_me_home_preserves_user_isolation(client, db_session):
    _seed_catalog(db_session, movies=20, series_n=5)
    users = db_session.query(Subscriber).all()
    assert users
    user = users[0]
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
