"""Public catalog locale query parameter behavior."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.content import Movie
from app.services.content_i18n import store_tmdb_locale_bundle, upsert_translation


def _published_movie(db_session, *, slug: str = "locale-movie") -> Movie:
    movie = Movie(
        title="Locale Movie",
        original_title="Locale Movie",
        slug=slug,
        description="Canonical English description",
        short_description="Canonical short",
        release_year=2020,
        status="published",
        published_at=datetime.now(UTC),
        language="en",
        imdb_rating=8.0,
        poster_url="https://example.com/p.jpg",
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def test_movie_detail_locale_fa_and_ps(client, db_session):
    movie = _published_movie(db_session, slug="locale-detail")
    store_tmdb_locale_bundle(
        db_session,
        entity_type="movie",
        entity_id=movie.id,
        locale="en",
        fields={"title": "English Localized", "overview": "English body"},
    )
    store_tmdb_locale_bundle(
        db_session,
        entity_type="movie",
        entity_id=movie.id,
        locale="fa",
        fields={"title": "عنوان فارسی", "overview": "توضیح فارسی"},
    )
    db_session.commit()

    en = client.get(f"/api/movies/{movie.id}", params={"locale": "en"})
    assert en.status_code == 200
    assert en.json()["title"] == "English Localized"
    assert en.json()["localization"]["sources"]["title"] in {"tmdb", "manual"}

    fa = client.get(f"/api/movies/{movie.id}", params={"locale": "fa"})
    assert fa.status_code == 200
    assert fa.json()["title"] == "عنوان فارسی"
    assert fa.json()["localization"]["sources"]["title"] == "tmdb"

    ps = client.get(f"/api/movies/{movie.id}", params={"locale": "ps"})
    assert ps.status_code == 200
    assert ps.json()["title"] == "English Localized"
    assert ps.json()["localization"]["sources"]["title"] == "fallback"


def test_movie_list_honors_locale(client, db_session):
    movie = _published_movie(db_session, slug="locale-list")
    store_tmdb_locale_bundle(
        db_session,
        entity_type="movie",
        entity_id=movie.id,
        locale="fa",
        fields={"title": "لیست فارسی"},
    )
    db_session.commit()
    res = client.get("/api/movies", params={"locale": "fa", "page_size": 100})
    assert res.status_code == 200
    items = res.json()["data"]
    match = next((m for m in items if m["id"] == movie.id), None)
    assert match is not None
    assert match["title"] == "لیست فارسی"


def test_manual_fa_beats_tmdb_on_detail(client, db_session):
    movie = _published_movie(db_session, slug="locale-manual")
    store_tmdb_locale_bundle(
        db_session,
        entity_type="movie",
        entity_id=movie.id,
        locale="fa",
        fields={"title": "TMDB فا"},
    )
    db_session.commit()
    upsert_translation(
        db_session,
        entity_type="movie",
        entity_id=movie.id,
        locale="fa",
        field_key="title",
        value="دستی فا",
        source="manual",
        overwrite_manual=True,
    )
    db_session.commit()
    res = client.get(f"/api/movies/{movie.id}", params={"locale": "fa"})
    assert res.status_code == 200
    assert res.json()["title"] == "دستی فا"
    assert res.json()["localization"]["sources"]["title"] == "manual"
