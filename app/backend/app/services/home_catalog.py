"""Bounded homepage catalog aggregation (anonymous + authenticated)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.content import Movie, Series
from app.models.user import Subscriber
from app.schemas.collections import CollectionItemOut, CollectionPublicOut
from app.services.catalog import apply_sort, filter_catalog_query
from app.services.catalog_list import movies_card_out, series_card_out
from app.services.collections import _is_content_publicly_visible, list_public_collections
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


def _unique_series(*groups: list[Series]) -> list[Series]:
    seen: set[int] = set()
    out: list[Series] = []
    for group in groups:
        for row in group:
            if row.id in seen:
                continue
            seen.add(row.id)
            out.append(row)
    return out


def _map_movie_cards(rows: list[Movie], card_by_id: dict[int, Any]) -> list:
    return [card_by_id[m.id] for m in rows if m.id in card_by_id]


def _anon_recommendation_item(movie: Movie, *, reason: str, playable: bool) -> dict[str, Any]:
    return {
        "content_type": "movie",
        "id": movie.id,
        "slug": movie.slug,
        "title": movie.title,
        "poster_url": movie.poster_url or "",
        "backdrop_url": movie.backdrop_url or "",
        "release_year": movie.release_year,
        "imdb_rating": movie.imdb_rating,
        "genres": [g.name for g in (movie.genre_links or [])],
        "score": 0.0,
        "reasons": [reason],
        "explanation": reason,
        "playable": bool(playable),
        "detail_path": f"/movie/{movie.slug}",
    }


def _collection_out_from_cards(
    collection,
    *,
    movie_cards: dict[int, Any],
    series_cards: dict[int, Any],
) -> CollectionPublicOut:
    items_out: list[CollectionItemOut] = []
    for item in sorted(collection.items or [], key=lambda i: (i.position, i.id)):
        movie = item.movie
        series = item.series
        if not _is_content_publicly_visible(movie, series):
            continue
        if item.movie_id is not None:
            payload = movie_cards.get(item.movie_id)
            if payload is None:
                continue
            items_out.append(
                CollectionItemOut(
                    id=item.id,
                    collection_id=item.collection_id,
                    movie_id=item.movie_id,
                    series_id=item.series_id,
                    position=item.position,
                    custom_title=item.custom_title,
                    custom_description=item.custom_description,
                    content_type="movie",
                    movie=payload,
                    series=None,
                    created_at=item.created_at,
                    publicly_visible=True,
                )
            )
        else:
            payload = series_cards.get(item.series_id) if item.series_id else None
            if payload is None:
                continue
            items_out.append(
                CollectionItemOut(
                    id=item.id,
                    collection_id=item.collection_id,
                    movie_id=item.movie_id,
                    series_id=item.series_id,
                    position=item.position,
                    custom_title=item.custom_title,
                    custom_description=item.custom_description,
                    content_type="series",
                    movie=None,
                    series=payload,
                    created_at=item.created_at,
                    publicly_visible=True,
                )
            )
    return CollectionPublicOut(
        id=collection.id,
        title=collection.title,
        slug=collection.slug,
        description=collection.description or "",
        short_description=collection.short_description or "",
        collection_type=collection.collection_type,
        poster_url=collection.poster_url or "",
        backdrop_url=collection.backdrop_url or "",
        sort_order=collection.sort_order,
        is_featured=bool(collection.is_featured),
        item_count=len(items_out),
        items=items_out,
        published_at=collection.published_at,
    )


def build_catalog_home(
    db: Session,
    *,
    locale: str | None = None,
    include_recommendations: bool = True,
) -> dict[str, Any]:
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
    # Newest pool also supplies the "recently added" shelf (saves a duplicate query).
    pool_rows = apply_sort(
        filter_catalog_query(_movie_q(db), Movie, published_only=True),
        Movie,
        "newest",
    ).limit(40).all()
    recently_rows = pool_rows[:12]
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

    series_rows = apply_sort(
        filter_catalog_query(_series_q(db), Series, published_only=True),
        Series,
        "views_desc",
    ).limit(12).all()

    collection_rows, _total = list_public_collections(
        db,
        featured_only=True,
        page=1,
        page_size=6,
        include_items=True,
        min_visible_items=1,
    )
    collection_movies = [
        item.movie
        for coll in collection_rows
        for item in (coll.items or [])
        if item.movie is not None
    ]
    collection_series = [
        item.series
        for coll in collection_rows
        for item in (coll.items or [])
        if item.series is not None
    ]

    all_movies = _unique_movies(
        featured_rows,
        trending_rows,
        recently_rows,
        top_rated_rows,
        action_rows,
        comedy_rows,
        pool_rows,
        collection_movies,
    )
    all_series = _unique_series(series_rows, collection_series)
    movie_cards = {c.id: c for c in movies_card_out(db, all_movies, locale=locale)}
    series_cards = {c.id: c for c in series_card_out(db, all_series, locale=locale)}

    featured = _map_movie_cards(featured_rows, movie_cards)
    trending = _map_movie_cards(trending_rows, movie_cards)
    recently_added = _map_movie_cards(recently_rows, movie_cards)
    top_rated = _map_movie_cards(top_rated_rows, movie_cards)
    action = _map_movie_cards(action_rows, movie_cards)
    comedy = _map_movie_cards(comedy_rows, movie_cards)
    pool = _map_movie_cards(pool_rows, movie_cards)

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

    popular_series = [series_cards[s.id] for s in series_rows if s.id in series_cards]
    featured_collections = [
        _collection_out_from_cards(row, movie_cards=movie_cards, series_cards=series_cards)
        for row in collection_rows
    ]

    recommendations = None
    if include_recommendations:
        playable_by_id = {mid: bool(card.playable) for mid, card in movie_cards.items()}
        used: set[int] = set()
        shelves: list[dict[str, Any]] = []

        def take(rows: list[Movie], *, reason: str, shelf_type: str, title: str) -> None:
            items = []
            for movie in rows:
                if movie.id in used:
                    continue
                used.add(movie.id)
                items.append(
                    _anon_recommendation_item(
                        movie,
                        reason=reason,
                        playable=playable_by_id.get(movie.id, False),
                    )
                )
                if len(items) >= 12:
                    break
            if items:
                shelves.append(
                    {
                        "shelf_type": shelf_type,
                        "title": title,
                        "personalized": False,
                        "items": items,
                    }
                )

        take(trending_rows, reason="Popular in the catalog", shelf_type="popular", title="Popular Now")
        take(recently_rows, reason="Recently added", shelf_type="new_releases", title="New Releases")
        take(top_rated_rows, reason="Top rated", shelf_type="top_rated", title="Top Rated")
        if collection_rows:
            shelves.append(
                {
                    "shelf_type": "editorial_collections",
                    "title": "Featured Collections",
                    "personalized": False,
                    "collections": [
                        {"id": c.id, "slug": c.slug, "title": c.title} for c in collection_rows
                    ],
                    "items": [],
                }
            )
        recommendations = {"mode": "anonymous", "personalized": False, "shelves": shelves}

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
        "recommendations": recommendations,
    }


def build_me_home(
    db: Session,
    subscriber: Subscriber,
    *,
    locale: str | None = None,
) -> dict[str, Any]:
    """Authenticated homepage: catalog shelves + personalized rails."""
    from app.services import watch_history as wh
    from app.services.recommendations.engine import home_recommendation_payload

    # Skip anonymous rec construction — personalized payload replaces it below.
    catalog = build_catalog_home(db, locale=locale, include_recommendations=False)
    cw = wh.list_continue_watching(db, subscriber)
    # Homepage only needs the first page of items; skip a separate COUNT(*).
    from app.models.user import WatchlistItem
    from app.services.watchlist import _serialize as _wl_serialize

    watch_q = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.subscriber_id == subscriber.id)
        .order_by(WatchlistItem.created_at.desc(), WatchlistItem.id.desc())
        .limit(20)
        .all()
    )
    watch_items = [_wl_serialize(db, row) for row in watch_q]
    recs = home_recommendation_payload(db, subscriber)
    return {
        **catalog,
        "continue_watching": cw,
        "watchlist": watch_items,
        "recommendations": recs,
    }
