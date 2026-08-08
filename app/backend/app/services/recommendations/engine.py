"""Recommendation engine: candidates, ranking, home shelves, what-to-watch."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.models.collections import Collection, CollectionItem
from app.models.content import Genre, Movie, Series, movie_genres, series_genres
from app.models.credits import MovieCastCredit, SeriesCastCredit
from app.models.user import Subscriber
from app.services.catalog import content_playability
from app.services.publishing.visibility import apply_public_visibility
from app.services.recommendations.cache import cache_get, cache_set, catalog_feature_epoch
from app.services.recommendations.moods import genres_for_mood, is_known_mood
from app.services.recommendations.profile import build_preference_profile, profile_public_summary
from app.services.recommendations.scoring import (
    CatalogFeature,
    score_candidate,
    short_explanation,
    stable_sort_key,
)
from app.services.recommendations.types import PreferenceProfile, ScoredCandidate
from app.services.recommendations.weights import (
    BECAUSE_MIN_CANDIDATES,
    BECAUSE_MIN_TOP_SCORE,
    CANDIDATE_CAST_LIMIT,
    CANDIDATE_COLLECTION_LIMIT,
    CANDIDATE_GENRE_LIMIT,
    CANDIDATE_POPULAR_LIMIT,
    CANDIDATE_RECENT_LIMIT,
    CANDIDATE_TOTAL_CAP,
    score_weights_from_settings,
)

ContentTypeFilter = Literal["movie", "series", "either", "any", None]


def _published_movies(db: Session):
    return apply_public_visibility(
        db.query(Movie).options(selectinload(Movie.genre_links)),
        Movie,
    )


def _published_series(db: Session):
    return apply_public_visibility(
        db.query(Series).options(selectinload(Series.genre_links)),
        Series,
    )


def _ts(dt: datetime | None) -> float:
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


def _movie_feature(
    db: Session,
    movie: Movie,
    *,
    cast_names: set[str] | None = None,
    cast_ids: set[int] | None = None,
    collection_ids: set[int] | None = None,
    playable: bool | None = None,
) -> CatalogFeature:
    if playable is None:
        playable, _, _ = content_playability(db, movie_id=movie.id)
    genres = [g.name for g in (movie.genre_links or [])]
    return CatalogFeature(
        kind="movie",
        id=movie.id,
        title=movie.title,
        slug=movie.slug,
        poster_url=movie.poster_url or "",
        backdrop_url=movie.backdrop_url or "",
        release_year=movie.release_year,
        imdb_rating=movie.imdb_rating,
        genres=genres,
        genre_slugs=[g.slug for g in (movie.genre_links or [])],
        language=movie.language or "",
        dubbed=[x for x in (movie.dubbed or []) if isinstance(x, str)],
        subtitles=[x for x in (movie.subtitles or []) if isinstance(x, str)],
        country=movie.country or "",
        duration_minutes=movie.duration_minutes,
        views=int(movie.views or 0),
        published_at_ts=_ts(movie.published_at),
        cast_names=cast_names or {str(n).strip() for n in (movie.cast or []) if n},
        cast_ids=cast_ids or set(),
        collection_ids=collection_ids or set(),
        playable=bool(playable),
    )


def _series_feature(
    db: Session,
    series: Series,
    *,
    cast_names: set[str] | None = None,
    cast_ids: set[int] | None = None,
    collection_ids: set[int] | None = None,
) -> CatalogFeature:
    genres = [g.name for g in (series.genre_links or [])]
    return CatalogFeature(
        kind="series",
        id=series.id,
        title=series.title,
        slug=series.slug,
        poster_url=series.poster_url or "",
        backdrop_url=series.backdrop_url or "",
        release_year=series.release_year,
        imdb_rating=series.imdb_rating,
        genres=genres,
        genre_slugs=[g.slug for g in (series.genre_links or [])],
        language=series.language or "",
        dubbed=[x for x in (series.dubbed or []) if isinstance(x, str)],
        subtitles=[x for x in (series.subtitles or []) if isinstance(x, str)],
        country=series.country or "",
        duration_minutes=None,
        views=int(series.views or 0),
        published_at_ts=_ts(series.published_at),
        cast_names=cast_names or set(),
        cast_ids=cast_ids or set(),
        collection_ids=collection_ids or set(),
        playable=False,
    )


def _candidate_pool(
    db: Session,
    profile: PreferenceProfile,
    *,
    content_type: str | None,
    genre: str | None,
    language: str | None,
    exclude: set[tuple[str, int]],
) -> list[CatalogFeature]:
    features: dict[tuple[str, int], CatalogFeature] = {}

    def add_movie(m: Movie, **extra: Any) -> None:
        key = ("movie", m.id)
        if key in exclude or key in features:
            return
        features[key] = _movie_feature(db, m, **extra)

    def add_series(s: Series, **extra: Any) -> None:
        key = ("series", s.id)
        if key in exclude or key in features:
            return
        features[key] = _series_feature(db, s, **extra)

    want_movies = content_type in (None, "", "either", "any", "movie")
    want_series = content_type in (None, "", "either", "any", "series")

    top_genres = list(profile.preferred_genres.keys())[:6]
    if genre:
        top_genres = [genre.strip().lower()] + top_genres

    if want_movies and top_genres:
        movie_genre_ids = [
            r[0]
            for r in (
                db.query(Genre.id)
                .filter(or_(func.lower(Genre.name).in_(top_genres), func.lower(Genre.slug).in_(top_genres)))
                .all()
            )
        ]
        if movie_genre_ids:
            q = (
                _published_movies(db)
                .join(movie_genres, movie_genres.c.movie_id == Movie.id)
                .filter(movie_genres.c.genre_id.in_(movie_genre_ids))
                .order_by(Movie.views.desc(), Movie.id.desc())
                .limit(CANDIDATE_GENRE_LIMIT)
            )
            if language:
                q = q.filter(func.lower(Movie.language) == language.strip().lower())
            for m in q.all():
                add_movie(m)

    if want_series and top_genres:
        gids = [
            r[0]
            for r in (
                db.query(Genre.id)
                .filter(or_(func.lower(Genre.name).in_(top_genres), func.lower(Genre.slug).in_(top_genres)))
                .all()
            )
        ]
        if gids:
            sq = (
                _published_series(db)
                .join(series_genres, series_genres.c.series_id == Series.id)
                .filter(series_genres.c.genre_id.in_(gids))
                .order_by(Series.views.desc(), Series.id.desc())
                .limit(CANDIDATE_GENRE_LIMIT)
            )
            if language:
                sq = sq.filter(func.lower(Series.language) == language.strip().lower())
            for s in sq.all():
                add_series(s)

    if want_movies:
        q = _published_movies(db).order_by(Movie.views.desc(), Movie.id.desc()).limit(CANDIDATE_POPULAR_LIMIT)
        if language:
            q = q.filter(func.lower(Movie.language) == language.strip().lower())
        for m in q.all():
            add_movie(m)
        q = (
            _published_movies(db)
            .order_by(Movie.published_at.desc(), Movie.id.desc())
            .limit(CANDIDATE_RECENT_LIMIT)
        )
        for m in q.all():
            add_movie(m)

    if want_series:
        q = _published_series(db).order_by(Series.views.desc(), Series.id.desc()).limit(CANDIDATE_POPULAR_LIMIT)
        if language:
            q = q.filter(func.lower(Series.language) == language.strip().lower())
        for s in q.all():
            add_series(s)
        q = (
            _published_series(db)
            .order_by(Series.published_at.desc(), Series.id.desc())
            .limit(CANDIDATE_RECENT_LIMIT)
        )
        for s in q.all():
            add_series(s)

    # Collection neighbors of watched/watchlisted titles.
    seed_movie_ids = list(profile.watched_movie_ids | profile.watchlisted_movie_ids)[:40]
    seed_series_ids = list(profile.watched_series_ids | profile.watchlisted_series_ids)[:40]
    collection_ids: set[int] = set()
    if seed_movie_ids or seed_series_ids:
        cq = (
            db.query(CollectionItem.collection_id)
            .join(Collection, Collection.id == CollectionItem.collection_id)
            .filter(
                Collection.deleted_at.is_(None),
                Collection.status == "published",
            )
        )
        parts = []
        if seed_movie_ids:
            parts.append(CollectionItem.movie_id.in_(seed_movie_ids))
        if seed_series_ids:
            parts.append(CollectionItem.series_id.in_(seed_series_ids))
        if parts:
            cq = cq.filter(or_(*parts))
            collection_ids = {r[0] for r in cq.distinct().limit(30).all()}
    if collection_ids:
        items = (
            db.query(CollectionItem)
            .filter(CollectionItem.collection_id.in_(collection_ids))
            .order_by(CollectionItem.position.asc(), CollectionItem.id.asc())
            .limit(CANDIDATE_COLLECTION_LIMIT * 2)
            .all()
        )
        mids = [i.movie_id for i in items if i.movie_id]
        sids = [i.series_id for i in items if i.series_id]
        if want_movies and mids:
            for m in _published_movies(db).filter(Movie.id.in_(mids)).limit(CANDIDATE_COLLECTION_LIMIT).all():
                add_movie(m, collection_ids={cid for cid in collection_ids})
        if want_series and sids:
            for s in _published_series(db).filter(Series.id.in_(sids)).limit(CANDIDATE_COLLECTION_LIMIT).all():
                add_series(s, collection_ids={cid for cid in collection_ids})

    # Cast overlap candidates.
    actor_ids = list(profile.preferred_actor_ids.keys())[:12]
    if actor_ids:
        if want_movies:
            mids = [
                r[0]
                for r in (
                    db.query(MovieCastCredit.movie_id)
                    .filter(MovieCastCredit.tmdb_person_id.in_(actor_ids))
                    .distinct()
                    .limit(CANDIDATE_CAST_LIMIT)
                    .all()
                )
            ]
            if mids:
                movie_credits = (
                    db.query(MovieCastCredit)
                    .filter(MovieCastCredit.movie_id.in_(mids), MovieCastCredit.tmdb_person_id.in_(actor_ids))
                    .all()
                )
                by_movie: dict[int, tuple[set[str], set[int]]] = {}
                for mc in movie_credits:
                    names, ids = by_movie.setdefault(mc.movie_id, (set(), set()))
                    names.add(mc.name)
                    ids.add(mc.tmdb_person_id)
                for m in _published_movies(db).filter(Movie.id.in_(mids)).all():
                    names, ids = by_movie.get(m.id, (set(), set()))
                    add_movie(m, cast_names=names | {str(n) for n in (m.cast or []) if n}, cast_ids=ids)
        if want_series:
            sids = [
                r[0]
                for r in (
                    db.query(SeriesCastCredit.series_id)
                    .filter(SeriesCastCredit.tmdb_person_id.in_(actor_ids))
                    .distinct()
                    .limit(CANDIDATE_CAST_LIMIT)
                    .all()
                )
            ]
            if sids:
                series_cast_rows: list[SeriesCastCredit] = (
                    db.query(SeriesCastCredit)
                    .filter(SeriesCastCredit.series_id.in_(sids), SeriesCastCredit.tmdb_person_id.in_(actor_ids))
                    .all()
                )
                by_series: dict[int, tuple[set[str], set[int]]] = {}
                for series_credit in series_cast_rows:
                    names, ids = by_series.setdefault(series_credit.series_id, (set(), set()))
                    names.add(series_credit.name)
                    ids.add(series_credit.tmdb_person_id)
                for s in _published_series(db).filter(Series.id.in_(sids)).all():
                    names, ids = by_series.get(s.id, (set(), set()))
                    add_series(s, cast_names=names, cast_ids=ids)

    # Annotate collection overlap ratio vs seed collections.
    if collection_ids:
        for feat in features.values():
            if feat.collection_ids:
                overlap = len(feat.collection_ids & collection_ids) / max(1, len(collection_ids))
                feat.collection_overlap = min(1.0, overlap * 3.0)

    # Optional genre hard filter after pooling.
    out = list(features.values())
    if genre:
        g = genre.strip().lower()
        out = [f for f in out if g in {x.lower() for x in f.genres} or g in {x.lower() for x in f.genre_slugs}]
    if language:
        lang = language.strip().lower()
        out = [
            f
            for f in out
            if f.language.lower() == lang
            or lang in {d.lower() for d in f.dubbed}
            or lang in {s.lower() for s in f.subtitles}
        ]
    return out[:CANDIDATE_TOTAL_CAP]


def _exclude_set(profile: PreferenceProfile, *, extra: set[tuple[str, int]] | None = None) -> set[tuple[str, int]]:
    exclude: set[tuple[str, int]] = set(extra or ())
    for mid in profile.completed_movie_ids:
        exclude.add(("movie", mid))
    for sid in profile.completed_series_ids:
        exclude.add(("series", sid))
    return exclude


def _rank(
    features: list[CatalogFeature],
    profile: PreferenceProfile,
    *,
    limit: int,
    settings: Settings,
    similar_to_title: str | None = None,
    exclude: set[tuple[str, int]] | None = None,
    min_score: float = 0.0,
) -> list[ScoredCandidate]:
    weights = score_weights_from_settings(settings)
    now_ts = datetime.now(UTC).timestamp()
    scored: list[ScoredCandidate] = []
    for feat in features:
        item = score_candidate(
            feat,
            profile,
            weights=weights,
            exclude_ids=exclude,
            similar_to_title=similar_to_title,
            now_ts=now_ts,
        )
        if item is None or item.score < min_score:
            continue
        scored.append(item)
    scored.sort(key=stable_sort_key)
    # Deduplicate by key (already unique) and stable truncate.
    seen: set[str] = set()
    out: list[ScoredCandidate] = []
    for item in scored:
        if item.key in seen:
            continue
        seen.add(item.key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def scored_to_public_dict(item: ScoredCandidate, *, include_components: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "content_type": item.kind,
        "id": item.id,
        "slug": item.slug,
        "title": item.title,
        "poster_url": item.poster_url,
        "backdrop_url": item.backdrop_url,
        "release_year": item.release_year,
        "imdb_rating": item.imdb_rating,
        "genres": item.genres,
        "score": item.score,
        "reasons": item.reasons,
        "explanation": short_explanation(item.reasons),
        "playable": item.playable,
        "detail_path": f"/movie/{item.slug}" if item.kind == "movie" else f"/series/{item.slug}",
    }
    if include_components:
        payload["components"] = item.components
    return payload


def anonymous_fallback(
    db: Session,
    *,
    limit: int = 12,
    content_type: str | None = None,
    genre: str | None = None,
    language: str | None = None,
) -> list[ScoredCandidate]:
    """Deterministic non-personalized shelves: trending → new → top rated."""
    profile = PreferenceProfile(subscriber_id=None, has_personal_signals=False)
    features = _candidate_pool(
        db,
        profile,
        content_type=content_type,
        genre=genre,
        language=language,
        exclude=set(),
    )
    # Force popularity/recency-forward scoring with empty prefs.
    settings = get_settings()
    ranked = _rank(features, profile, limit=limit, settings=settings, min_score=0.0)
    # Relabel reasons for anonymous honesty.
    for item in ranked:
        item.reasons = ["Popular in the catalog"] if item.views >= 1 else ["Featured in the catalog"]
        if item.release_year and item.release_year >= datetime.now(UTC).year - 2:
            item.reasons = ["Recently added"]
    return ranked


def recommend_for_user(
    db: Session,
    subscriber: Subscriber | None,
    *,
    limit: int = 12,
    content_type: str | None = None,
    genre: str | None = None,
    language: str | None = None,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> tuple[list[ScoredCandidate], PreferenceProfile, str]:
    """Returns (items, profile, mode) where mode is personalized|popular."""
    settings = settings or get_settings()
    limit = max(1, min(int(limit), 40))
    cache_key = None
    if use_cache and subscriber is not None:
        cache_key = (
            f"u:{subscriber.id}:rec:{catalog_feature_epoch()}:"
            f"{limit}:{content_type}:{genre}:{language}"
        )
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

    profile = build_preference_profile(db, subscriber, settings=settings)
    if subscriber is None or not profile.has_personal_signals:
        items = anonymous_fallback(
            db, limit=limit, content_type=content_type, genre=genre, language=language
        )
        result = (items, profile, "popular")
        if cache_key:
            cache_set(cache_key, result)
        return result

    exclude = _exclude_set(profile)
    features = _candidate_pool(
        db,
        profile,
        content_type=content_type,
        genre=genre,
        language=language,
        exclude=exclude,
    )
    items = _rank(features, profile, limit=limit, settings=settings, exclude=exclude, min_score=0.12)
    if len(items) < min(3, limit):
        # Soft-fill from anonymous pool without pretending personalization for fillers.
        fill = anonymous_fallback(db, limit=limit, content_type=content_type, genre=genre, language=language)
        seen = {i.key for i in items}
        for row in fill:
            if row.key in seen:
                continue
            items.append(row)
            seen.add(row.key)
            if len(items) >= limit:
                break
    result = (items, profile, "personalized")
    if cache_key:
        cache_set(cache_key, result)
    return result


def recommend_for_item(
    db: Session,
    *,
    kind: Literal["movie", "series"],
    id_or_slug: str,
    limit: int = 12,
    settings: Settings | None = None,
) -> list[ScoredCandidate]:
    settings = settings or get_settings()
    limit = max(1, min(int(limit), 40))
    if kind == "movie":
        q = apply_public_visibility(db.query(Movie).options(selectinload(Movie.genre_links)), Movie)
        source = q.filter(or_(Movie.slug == id_or_slug, Movie.id == _as_int(id_or_slug))).first()
        if source is None:
            return []
        profile = PreferenceProfile(subscriber_id=None, has_personal_signals=True)
        for g in source.genre_links or []:
            profile.preferred_genres[g.name.lower()] = 1.0
        profile.preferred_languages[(source.language or "").lower()] = 1.0 if source.language else 0
        # Cast
        movie_credits = (
            db.query(MovieCastCredit)
            .filter(MovieCastCredit.movie_id == source.id)
            .order_by(MovieCastCredit.credit_order.asc())
            .limit(10)
            .all()
        )
        for mc in movie_credits:
            profile.preferred_actors[mc.name.lower()] = 1.0
            profile.preferred_actor_ids[mc.tmdb_person_id] = 1.0
        exclude = {("movie", source.id)}
        features = _candidate_pool(db, profile, content_type="movie", genre=None, language=None, exclude=exclude)
        return _rank(
            features,
            profile,
            limit=limit,
            settings=settings,
            similar_to_title=source.title,
            exclude=exclude,
            min_score=0.1,
        )

    q = apply_public_visibility(db.query(Series).options(selectinload(Series.genre_links)), Series)
    source = q.filter(or_(Series.slug == id_or_slug, Series.id == _as_int(id_or_slug))).first()
    if source is None:
        return []
    profile = PreferenceProfile(subscriber_id=None, has_personal_signals=True)
    for g in source.genre_links or []:
        profile.preferred_genres[g.name.lower()] = 1.0
    if source.language:
        profile.preferred_languages[source.language.lower()] = 1.0
    item_series_credits: list[SeriesCastCredit] = (
        db.query(SeriesCastCredit)
        .filter(SeriesCastCredit.series_id == source.id)
        .order_by(SeriesCastCredit.credit_order.asc())
        .limit(10)
        .all()
    )
    for series_credit in item_series_credits:
        profile.preferred_actors[series_credit.name.lower()] = 1.0
        profile.preferred_actor_ids[series_credit.tmdb_person_id] = 1.0
    exclude = {("series", source.id)}
    features = _candidate_pool(db, profile, content_type="series", genre=None, language=None, exclude=exclude)
    return _rank(
        features,
        profile,
        limit=limit,
        settings=settings,
        similar_to_title=source.title,
        exclude=exclude,
        min_score=0.1,
    )


def _as_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def because_you_watched_shelves(
    db: Session,
    subscriber: Subscriber,
    *,
    max_shelves: int = 2,
    per_shelf: int = 10,
    settings: Settings | None = None,
    used_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    profile = build_preference_profile(db, subscriber, settings=settings)
    used = set(used_keys or ())
    shelves: list[dict[str, Any]] = []
    for kind, cid, title, strength in profile.seed_titles:
        if len(shelves) >= max_shelves:
            break
        if strength < 0.4:
            continue
        exclude = _exclude_set(profile, extra={(kind, cid)})
        # Build a seed-local profile emphasizing this title's genres/cast.
        seed_profile = PreferenceProfile(
            subscriber_id=subscriber.id,
            preferred_genres=dict(profile.preferred_genres),
            preferred_languages=dict(profile.preferred_languages),
            preferred_actors=dict(profile.preferred_actors),
            preferred_actor_ids=dict(profile.preferred_actor_ids),
            watched_movie_ids=set(profile.watched_movie_ids),
            watched_series_ids=set(profile.watched_series_ids),
            completed_movie_ids=set(profile.completed_movie_ids),
            completed_series_ids=set(profile.completed_series_ids),
            has_personal_signals=True,
        )
        if kind == "movie":
            movie = (
                db.query(Movie)
                .options(selectinload(Movie.genre_links))
                .filter(Movie.id == cid)
                .first()
            )
            if movie is None:
                continue
            seed_profile.preferred_genres = {g.name.lower(): 1.5 for g in (movie.genre_links or [])}
            if movie.language:
                seed_profile.preferred_languages = {movie.language.lower(): 1.0}
        else:
            series = (
                db.query(Series)
                .options(selectinload(Series.genre_links))
                .filter(Series.id == cid)
                .first()
            )
            if series is None:
                continue
            seed_profile.preferred_genres = {g.name.lower(): 1.5 for g in (series.genre_links or [])}

        features = _candidate_pool(
            db,
            seed_profile,
            content_type="either",
            genre=None,
            language=None,
            exclude=exclude,
        )
        ranked = _rank(
            features,
            seed_profile,
            limit=per_shelf + 6,
            settings=settings,
            similar_to_title=title,
            exclude=exclude,
            min_score=BECAUSE_MIN_TOP_SCORE,
        )
        items = [r for r in ranked if r.key not in used]
        if len(items) < BECAUSE_MIN_CANDIDATES:
            continue
        if items[0].score < BECAUSE_MIN_TOP_SCORE:
            continue
        shelf_items = items[:per_shelf]
        for it in shelf_items:
            used.add(it.key)
        shelves.append(
            {
                "shelf_type": "because_you_watched",
                "title": f"Because You Watched {title}",
                "source": {"content_type": kind, "id": cid, "title": title},
                "personalized": True,
                "items": [scored_to_public_dict(i) for i in shelf_items],
            }
        )
    return shelves


def _editorial_collection_titles(db: Session, *, limit: int = 4) -> list[dict[str, Any]]:
    rows = (
        db.query(Collection)
        .filter(
            Collection.deleted_at.is_(None),
            Collection.status == "published",
            Collection.is_featured.is_(True),
        )
        .order_by(Collection.sort_order.asc(), Collection.id.desc())
        .limit(limit)
        .all()
    )
    return [{"id": c.id, "slug": c.slug, "title": c.title} for c in rows]


def home_recommendation_payload(
    db: Session,
    subscriber: Subscriber | None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    used: set[str] = set()
    shelves: list[dict[str, Any]] = []

    if subscriber is None:
        popular = anonymous_fallback(db, limit=12)
        new_items = (
            _published_movies(db)
            .order_by(Movie.published_at.desc(), Movie.id.desc())
            .limit(12)
            .all()
        )
        top_rated = (
            _published_movies(db)
            .order_by(Movie.imdb_rating.desc(), Movie.views.desc(), Movie.id.desc())
            .limit(12)
            .all()
        )
        shelves.append(
            {
                "shelf_type": "popular",
                "title": "Popular Now",
                "personalized": False,
                "items": [scored_to_public_dict(i) for i in popular],
            }
        )
        used.update(i.key for i in popular)
        new_scored = []
        for m in new_items:
            feat = _movie_feature(db, m)
            if feat.key in used:
                continue
            item = score_candidate(feat, PreferenceProfile(subscriber_id=None), now_ts=datetime.now(UTC).timestamp())
            if item:
                item.reasons = ["Recently added"]
                new_scored.append(item)
                used.add(item.key)
            if len(new_scored) >= 12:
                break
        if new_scored:
            shelves.append(
                {
                    "shelf_type": "new_releases",
                    "title": "New Releases",
                    "personalized": False,
                    "items": [scored_to_public_dict(i) for i in new_scored],
                }
            )
        rated = []
        for m in top_rated:
            key = f"movie:{m.id}"
            if key in used:
                continue
            feat = _movie_feature(db, m)
            item = score_candidate(feat, PreferenceProfile(subscriber_id=None))
            if item:
                item.reasons = ["Top rated"]
                rated.append(item)
                used.add(item.key)
            if len(rated) >= 12:
                break
        if rated:
            shelves.append(
                {
                    "shelf_type": "top_rated",
                    "title": "Top Rated",
                    "personalized": False,
                    "items": [scored_to_public_dict(i) for i in rated],
                }
            )
        editorial = _editorial_collection_titles(db)
        if editorial:
            shelves.append(
                {
                    "shelf_type": "editorial_collections",
                    "title": "Featured Collections",
                    "personalized": False,
                    "collections": editorial,
                    "items": [],
                }
            )
        return {"mode": "anonymous", "personalized": False, "shelves": shelves}

    items, profile, mode = recommend_for_user(db, subscriber, limit=16, settings=settings)
    if mode == "personalized" and items:
        rec_items = []
        for i in items:
            if i.key in used:
                continue
            rec_items.append(i)
            used.add(i.key)
            if len(rec_items) >= 12:
                break
        if rec_items:
            shelves.append(
                {
                    "shelf_type": "recommended",
                    "title": "Recommended for You",
                    "personalized": True,
                    "items": [scored_to_public_dict(i) for i in rec_items],
                }
            )
    else:
        popular = anonymous_fallback(db, limit=12)
        shelves.append(
            {
                "shelf_type": "popular",
                "title": "Popular Now",
                "personalized": False,
                "items": [scored_to_public_dict(i) for i in popular],
            }
        )
        used.update(i.key for i in popular)

    shelves.extend(
        because_you_watched_shelves(
            db, subscriber, max_shelves=2, per_shelf=10, settings=settings, used_keys=used
        )
    )
    for shelf in shelves:
        for it in shelf.get("items") or []:
            used.add(f"{it['content_type']}:{it['id']}")

    return {
        "mode": mode,
        "personalized": mode == "personalized",
        "preference_summary": {
            "top_genres": list(profile.preferred_genres.keys())[:5],
            "has_personal_signals": profile.has_personal_signals,
        },
        "shelves": shelves,
    }


def what_to_watch(
    db: Session,
    *,
    content_type: str = "either",
    genre: str | None = None,
    mood: str | None = None,
    duration: str | None = None,
    language: str | None = None,
    subtitles: str | None = None,
    release_period: str | None = None,
    limit: int = 8,
    subscriber: Subscriber | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Guided discovery — deterministic filters + light preference boost. Not AI."""
    settings = settings or get_settings()
    limit = max(3, min(int(limit), 10))
    if mood and not is_known_mood(mood):
        mood = None
    mood_genres = genres_for_mood(mood)
    profile = build_preference_profile(db, subscriber, settings=settings)

    # Seed genre prefs from mood/genre filters so scoring explains matches.
    guide_profile = PreferenceProfile(
        subscriber_id=profile.subscriber_id,
        preferred_genres=dict(profile.preferred_genres),
        preferred_languages=dict(profile.preferred_languages),
        preferred_dubbed_languages=dict(profile.preferred_dubbed_languages),
        preferred_subtitle_languages=dict(profile.preferred_subtitle_languages),
        preferred_actors=dict(profile.preferred_actors),
        preferred_actor_ids=dict(profile.preferred_actor_ids),
        watched_movie_ids=set(profile.watched_movie_ids),
        watched_series_ids=set(profile.watched_series_ids),
        completed_movie_ids=set(profile.completed_movie_ids),
        completed_series_ids=set(profile.completed_series_ids),
        has_personal_signals=True,
    )
    for g in mood_genres:
        guide_profile.preferred_genres[g.lower()] = max(guide_profile.preferred_genres.get(g.lower(), 0), 1.2)
    if genre:
        guide_profile.preferred_genres[genre.strip().lower()] = max(
            guide_profile.preferred_genres.get(genre.strip().lower(), 0), 1.4
        )

    exclude = _exclude_set(guide_profile)
    features = _candidate_pool(
        db,
        guide_profile,
        content_type=content_type,
        genre=genre,
        language=None if language in (None, "", "any") else language,
        exclude=exclude,
    )

    year_now = datetime.now(UTC).year
    filtered: list[CatalogFeature] = []
    for feat in features:
        if duration and feat.kind == "movie":
            mins = feat.duration_minutes
            if mins is not None:
                d = duration.strip().lower()
                if d in ("under_90", "under 90 min", "<90") and mins >= 90:
                    continue
                if d in ("90_120", "90–120 min", "90-120") and not (90 <= mins <= 120):
                    continue
                if d in ("over_120", "over 120 min", ">120") and mins <= 120:
                    continue
            elif duration.strip().lower() not in ("any", ""):
                # Series or unknown runtime: keep series for non-movie duration filters lightly.
                if feat.kind == "movie":
                    continue
        if language and language.strip().lower() not in ("any", "original", ""):
            lang = language.strip().lower()
            # Persian/Dari/Pashto dub where metadata exists
            dubbed_norm = {x.lower() for x in feat.dubbed}
            spoken = feat.language.lower()
            aliases = {
                "persian": {"persian", "farsi", "fa", "dari"},
                "dari": {"dari", "persian", "farsi", "fa"},
                "pashto": {"pashto", "ps", "pushto"},
                "farsi": {"farsi", "persian", "fa", "dari"},
            }
            accepted = aliases.get(lang, {lang})
            if not (spoken in accepted or dubbed_norm & accepted):
                continue
        if subtitles and subtitles.strip().lower() == "required":
            if not feat.subtitles:
                continue
        if release_period and release_period.strip().lower() not in ("any", ""):
            rp = release_period.strip().lower()
            year = feat.release_year or 0
            if rp == "new" and year < year_now - 2:
                continue
            if rp == "modern" and not (year_now - 15 <= year <= year_now):
                continue
            if rp == "classic" and (year == 0 or year > year_now - 25):
                continue
        # Mood filter: require at least one mood genre when mood set.
        if mood_genres:
            names = {g.lower() for g in feat.genres}
            if not names.intersection({g.lower() for g in mood_genres}):
                continue
        filtered.append(feat)

    ranked = _rank(
        filtered,
        guide_profile,
        limit=limit,
        settings=settings,
        exclude=exclude,
        min_score=0.05,
    )
    # Ensure explainable mood/genre reasons first.
    for item in ranked:
        reasons = list(item.reasons)
        if mood_genres:
            hit = next((g for g in item.genres if g in mood_genres or g.lower() in {x.lower() for x in mood_genres}), None)
            if hit:
                mood_label = (mood or "").strip().capitalize() or "selected mood"
                prefix = f"Fits {mood_label} ({hit})"
                reasons = [prefix] + [r for r in reasons if r != prefix]
        if genre:
            reasons = [f"Matches {genre} genre"] + [r for r in reasons if "genre" not in r.lower()]
        item.reasons = reasons[:4]

    return {
        "mode": "what_to_watch",
        "ai": False,
        "filters": {
            "content_type": content_type,
            "genre": genre,
            "mood": mood,
            "mood_genres": mood_genres,
            "duration": duration,
            "language": language,
            "subtitles": subtitles,
            "release_period": release_period,
        },
        "count": len(ranked),
        "items": [scored_to_public_dict(i) for i in ranked],
    }


def inspect_recommendations(
    db: Session,
    *,
    subscriber_id: int,
    limit: int = 20,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Admin debug inspection — no auth/session secrets."""
    settings = settings or get_settings()
    user = db.get(Subscriber, subscriber_id)
    if user is None:
        return {"error": "subscriber_not_found", "subscriber_id": subscriber_id}
    items, profile, mode = recommend_for_user(
        db, user, limit=limit, settings=settings, use_cache=False
    )
    return {
        "subscriber_id": user.id,
        "username": user.username,
        "mode": mode,
        "preference_signals": profile_public_summary(profile),
        "weights": score_weights_from_settings(settings).__dict__,
        "candidates": [scored_to_public_dict(i, include_components=True) for i in items],
    }
