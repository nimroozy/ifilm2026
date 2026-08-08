"""Bounded homepage catalog aggregation (anonymous + authenticated)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.content import Movie, Series
from app.models.user import Subscriber
from app.services.catalog import apply_sort, filter_catalog_query
from app.services.catalog_list import movies_card_out, series_card_out
from app.services.collections import list_public_collections
from app.services.publishing.visibility import apply_public_visibility


def _movie_q(db: Session):
    return apply_public_visibility(
        db.query(Movie).options(joinedload(Movie.genre_links)),
        Movie,
    )


def _series_q(db: Session):
    return apply_public_visibility(
        db.query(Series).options(joinedload(Series.genre_links)),
        Series,
    )


def _unique_movies(*groups: list[Movie]) -> list[Movie]:
    seen: set[int] = set()
    out: list[Movie] = []
    for group in groups:
        for movie in group:
            if movie.id in seen:
                continue
            seen.add(movie.id)
            out.append(movie)
    return out


def _map_movie_cards(rows: list[Movie], card_by_id: dict[int, Any]) -> list:
    return [card_by_id[m.id] for m in rows if m.id in card_by_id]


def build_catalog_home(db: Session, *, locale: str | None = None) -> dict[str, Any]:
    """Anonymous/public homepage shelves with bounded card payloads."""
    featured_rows = apply_sort(
        filter_catalog_query(_movie_q(db), Movie, featured=True, published_only=True),
        Movie,
        "newest",
    ).limit(8).all()
    trending_rows = apply_sort(
        filter_catalog_query(_movie_q(db), Movie, trending=True, published_only=True),
        Movie,
        "views_desc",
    ).limit(12).all()
    if not trending_rows:
        trending_rows = apply_sort(
            filter_catalog_query(_movie_q(db), Movie, published_only=True),
            Movie,
            "views_desc",
        ).limit(12).all()
    recently_rows = apply_sort(
        filter_catalog_query(_movie_q(db), Movie, published_only=True),
        Movie,
        "newest",
    ).limit(12).all()
    top_rated_rows = apply_sort(
        filter_catalog_query(_movie_q(db), Movie, published_only=True),
        Movie,
        "rating_desc",
    ).limit(12).all()
    action_rows = apply_sort(
        filter_catalog_query(_movie_q(db), Movie, genre="Action", published_only=True),
        Movie,
        "views_desc",
    ).limit(12).all()
    comedy_rows = apply_sort(
        filter_catalog_query(_movie_q(db), Movie, genre="Comedy", published_only=True),
        Movie,
        "views_desc",
    ).limit(12).all()
    pool_rows = apply_sort(
        filter_catalog_query(_movie_q(db), Movie, published_only=True),
        Movie,
        "newest",
    ).limit(40).all()

    all_movies = _unique_movies(
        featured_rows,
        trending_rows,
        recently_rows,
        top_rated_rows,
        action_rows,
        comedy_rows,
        pool_rows,
    )
    cards = movies_card_out(db, all_movies, locale=locale)
    card_by_id = {c.id: c for c in cards}

    featured = _map_movie_cards(featured_rows, card_by_id)
    trending = _map_movie_cards(trending_rows, card_by_id)
    recently_added = _map_movie_cards(recently_rows, card_by_id)
    top_rated = _map_movie_cards(top_rated_rows, card_by_id)
    action = _map_movie_cards(action_rows, card_by_id)
    comedy = _map_movie_cards(comedy_rows, card_by_id)
    pool = _map_movie_cards(pool_rows, card_by_id)

    def has_dub(item, code: str) -> bool:
        audio = item.audio_availability
        langs = list(getattr(audio, "dubbed_languages", None) or [])
        if code in langs:
            return True
        needle = "persian" if code == "fa" else "pashto" if code == "ps" else code
        return any(needle in str(d).lower() for d in (item.dubbed or []))

    afghan = [m for m in pool if (m.country or "") == "Afghanistan"][:12]
    persian_dubbed = [m for m in pool if has_dub(m, "fa")][:12]
    pashto_dubbed = [m for m in pool if has_dub(m, "ps")][:12]
    family = [
        m
        for m in pool
        if any(g.name in {"Family", "Animation"} for g in (m.genres or []))
    ][:12]

    popular_series = series_card_out(
        db,
        apply_sort(
            filter_catalog_query(_series_q(db), Series, published_only=True),
            Series,
            "views_desc",
        )
        .limit(12)
        .all(),
        locale=locale,
    )

    from app.services import collections as collections_service

    collection_rows, _total = list_public_collections(
        db,
        featured_only=True,
        page=1,
        page_size=6,
        include_items=True,
        min_visible_items=1,
    )
    featured_collections = [
        collections_service.collection_public_out_cards(row, db, include_items=True, locale=locale)
        for row in collection_rows
    ]

    return {
        "featured": featured,
        "trending": trending,
        "recently_added": recently_added,
        "top_rated": top_rated,
        "action": action,
        "comedy": comedy,
        "afghan": afghan,
        "persian_dubbed": persian_dubbed,
        "pashto_dubbed": pashto_dubbed,
        "family": family,
        "popular_series": popular_series,
        "featured_collections": featured_collections,
    }


def build_me_home(
    db: Session,
    subscriber: Subscriber,
    *,
    locale: str | None = None,
) -> dict[str, Any]:
    """Authenticated homepage: catalog shelves + personalized rails."""
    from app.services import watch_history as wh
    from app.services import watchlist as wl
    from app.services.recommendations.engine import home_recommendation_payload

    catalog = build_catalog_home(db, locale=locale)
    cw = wh.list_continue_watching(db, subscriber)
    watch_items, _total = wl.list_watchlist(db, subscriber, page=1, page_size=20)
    recs = home_recommendation_payload(db, subscriber)
    return {
        **catalog,
        "continue_watching": cw,
        "watchlist": watch_items,
        "recommendations": recs,
    }
