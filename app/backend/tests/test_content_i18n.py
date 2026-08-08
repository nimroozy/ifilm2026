"""Localized catalog metadata resolution and TMDB sync rules."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.content_i18n import (
    resolve_text,
    store_tmdb_locale_bundle,
    upsert_translation,
)


def test_fa_prefers_manual_then_tmdb_then_english_fallback(db_session):
    movie_id = 101
    store_tmdb_locale_bundle(
        db_session,
        entity_type="movie",
        entity_id=movie_id,
        locale="en",
        fields={"title": "Inception", "overview": "English overview"},
    )
    store_tmdb_locale_bundle(
        db_session,
        entity_type="movie",
        entity_id=movie_id,
        locale="fa",
        fields={"title": "تلقین", "overview": "توضیح فارسی"},
    )
    db_session.commit()

    title, src = resolve_text(
        db_session,
        entity_type="movie",
        entity_id=movie_id,
        field_key="title",
        locale="fa",
        canonical="Inception",
    )
    assert title == "تلقین"
    assert src == "tmdb"

    upsert_translation(
        db_session,
        entity_type="movie",
        entity_id=movie_id,
        locale="fa",
        field_key="title",
        value="عنوان دستی",
        source="manual",
    )
    db_session.commit()
    title, src = resolve_text(
        db_session,
        entity_type="movie",
        entity_id=movie_id,
        field_key="title",
        locale="fa",
        canonical="Inception",
    )
    assert title == "عنوان دستی"
    assert src == "manual"


def test_fa_missing_translation_falls_back_to_english(db_session):
    movie_id = 102
    store_tmdb_locale_bundle(
        db_session,
        entity_type="movie",
        entity_id=movie_id,
        locale="en",
        fields={"title": "Arrival", "overview": "English only"},
    )
    db_session.commit()
    title, src = resolve_text(
        db_session,
        entity_type="movie",
        entity_id=movie_id,
        field_key="title",
        locale="fa",
        canonical="Arrival",
    )
    assert title == "Arrival"
    assert src == "fallback"


def test_ps_never_uses_persian_fallback(db_session):
    movie_id = 103
    store_tmdb_locale_bundle(
        db_session,
        entity_type="movie",
        entity_id=movie_id,
        locale="en",
        fields={"title": "Dune", "overview": "English overview"},
    )
    store_tmdb_locale_bundle(
        db_session,
        entity_type="movie",
        entity_id=movie_id,
        locale="fa",
        fields={"title": "تلماسه", "overview": "فارسی"},
    )
    db_session.commit()
    title, src = resolve_text(
        db_session,
        entity_type="movie",
        entity_id=movie_id,
        field_key="title",
        locale="ps",
        canonical="Dune",
    )
    assert title == "Dune"
    assert src == "fallback"
    assert title != "تلماسه"


def test_tmdb_refresh_does_not_overwrite_manual(db_session):
    movie_id = 104
    upsert_translation(
        db_session,
        entity_type="movie",
        entity_id=movie_id,
        locale="fa",
        field_key="description",
        value="متن دستی ادمین",
        source="manual",
    )
    db_session.commit()
    store_tmdb_locale_bundle(
        db_session,
        entity_type="movie",
        entity_id=movie_id,
        locale="fa",
        fields={"overview": "متن TMDB"},
    )
    db_session.commit()
    value, src = resolve_text(
        db_session,
        entity_type="movie",
        entity_id=movie_id,
        field_key="description",
        locale="fa",
        canonical="English",
    )
    assert value == "متن دستی ادمین"
    assert src == "manual"


def test_series_and_episode_localization(db_session):
    store_tmdb_locale_bundle(
        db_session,
        entity_type="series",
        entity_id=11,
        locale="fa",
        fields={"title": "مجموعه فارسی", "overview": "شرح سریال"},
    )
    store_tmdb_locale_bundle(
        db_session,
        entity_type="episode",
        entity_id=22,
        locale="fa",
        fields={"title": "قسمت یک", "overview": "شرح قسمت"},
    )
    db_session.commit()
    series_title, series_src = resolve_text(
        db_session,
        entity_type="series",
        entity_id=11,
        field_key="title",
        locale="fa",
        canonical="Show",
    )
    ep_title, ep_src = resolve_text(
        db_session,
        entity_type="episode",
        entity_id=22,
        field_key="title",
        locale="fa",
        canonical="Episode",
    )
    assert series_title == "مجموعه فارسی"
    assert series_src == "tmdb"
    assert ep_title == "قسمت یک"
    assert ep_src == "tmdb"


def test_en_uses_english_metadata(db_session):
    movie = SimpleNamespace(id=105, title="Canonical", description="Canon desc")
    store_tmdb_locale_bundle(
        db_session,
        entity_type="movie",
        entity_id=movie.id,
        locale="en",
        fields={"title": "English Title", "overview": "English Desc"},
    )
    db_session.commit()
    title, src = resolve_text(
        db_session,
        entity_type="movie",
        entity_id=movie.id,
        field_key="title",
        locale="en",
        canonical=movie.title,
    )
    assert title == "English Title"
    assert src == "tmdb"
