"""Build a lightweight derived preference profile from user activity."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.models.content import Episode, Movie, Series
from app.models.credits import MovieCastCredit, SeriesCastCredit
from app.models.user import Subscriber, WatchlistItem
from app.models.watch_progress import UserWatchProgress
from app.services.publishing.visibility import movie_is_public, series_is_public
from app.services.recommendations.types import PreferenceProfile
from app.services.recommendations.weights import signal_weights_from_settings


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _add_weight(bucket: dict[str, float], key: str | None, weight: float) -> None:
    k = _norm(key)
    if not k or abs(weight) < 1e-9:
        return
    bucket[k] = bucket.get(k, 0.0) + weight


def _add_id_weight(bucket: dict[int, float], key: int | None, weight: float) -> None:
    if key is None or abs(weight) < 1e-9:
        return
    bucket[int(key)] = bucket.get(int(key), 0.0) + weight


def _top_n(bucket: dict[str, float], n: int = 12) -> dict[str, float]:
    items = sorted(bucket.items(), key=lambda kv: (-kv[1], kv[0]))
    return {k: round(v, 4) for k, v in items[:n] if v > 0}


def _signal_strength(
    *,
    completed: bool,
    progress_percent: float,
    position_seconds: float,
    hidden_from_continue: bool,
    min_seconds: float,
    signals,
) -> float:
    if hidden_from_continue:
        return float(signals.dismissed)
    if completed or progress_percent >= 90:
        return float(signals.completed)
    if progress_percent > 70:
        return float(signals.watched_high)
    if progress_percent >= 30:
        return float(signals.watched_medium)
    if position_seconds < min_seconds:
        return float(signals.very_short)
    # In-progress continue-watching band
    return float(signals.continue_watching)


def build_preference_profile(
    db: Session,
    subscriber: Subscriber | None,
    *,
    settings: Settings | None = None,
) -> PreferenceProfile:
    settings = settings or get_settings()
    signals = signal_weights_from_settings(settings)
    min_seconds = float(getattr(settings, "watch_progress_min_seconds", 30) or 30)

    if subscriber is None:
        return PreferenceProfile(subscriber_id=None, has_personal_signals=False)

    profile = PreferenceProfile(subscriber_id=subscriber.id)
    genre_w: dict[str, float] = defaultdict(float)
    type_w: dict[str, float] = defaultdict(float)
    lang_w: dict[str, float] = defaultdict(float)
    dub_w: dict[str, float] = defaultdict(float)
    sub_w: dict[str, float] = defaultdict(float)
    country_w: dict[str, float] = defaultdict(float)
    actor_w: dict[str, float] = defaultdict(float)
    actor_id_w: dict[int, float] = defaultdict(float)
    runtimes: list[int] = []
    years: list[int] = []
    seed_candidates: list[tuple[str, int, str, float, float]] = []  # kind,id,title,strength,ts

    progress_rows = (
        db.query(UserWatchProgress)
        .filter(UserWatchProgress.subscriber_id == subscriber.id)
        .order_by(UserWatchProgress.last_watched_at.desc())
        .limit(200)
        .all()
    )

    movie_ids = {r.movie_id for r in progress_rows if r.movie_id}
    episode_ids = {r.episode_id for r in progress_rows if r.episode_id}
    episodes = {
        e.id: e
        for e in (
            db.query(Episode)
            .options(selectinload(Episode.series).selectinload(Series.genre_links))
            .filter(Episode.id.in_(episode_ids))
            .all()
            if episode_ids
            else []
        )
    }
    series_ids_from_eps = {e.series_id for e in episodes.values() if e.series_id}
    movies = {
        m.id: m
        for m in (
            db.query(Movie)
            .options(selectinload(Movie.genre_links))
            .filter(Movie.id.in_(movie_ids))
            .all()
            if movie_ids
            else []
        )
    }
    series_map = {
        s.id: s
        for s in (
            db.query(Series)
            .options(selectinload(Series.genre_links))
            .filter(Series.id.in_(series_ids_from_eps))
            .all()
            if series_ids_from_eps
            else []
        )
    }

    # Cast credits for watched movies/series (bounded).
    movie_cast: dict[int, list[MovieCastCredit]] = defaultdict(list)
    if movie_ids:
        for mc_row in (
            db.query(MovieCastCredit)
            .filter(MovieCastCredit.movie_id.in_(movie_ids))
            .order_by(MovieCastCredit.credit_order.asc())
            .limit(800)
            .all()
        ):
            if len(movie_cast[mc_row.movie_id]) < 8:
                movie_cast[mc_row.movie_id].append(mc_row)
    series_cast: dict[int, list[SeriesCastCredit]] = defaultdict(list)
    if series_ids_from_eps:
        for sc_row in (
            db.query(SeriesCastCredit)
            .filter(SeriesCastCredit.series_id.in_(series_ids_from_eps))
            .order_by(SeriesCastCredit.credit_order.asc())
            .limit(800)
            .all()
        ):
            if len(series_cast[sc_row.series_id]) < 8:
                series_cast[sc_row.series_id].append(sc_row)

    for progress in progress_rows:
        strength = _signal_strength(
            completed=bool(progress.completed),
            progress_percent=float(progress.progress_percent or 0),
            position_seconds=float(progress.position_seconds or 0),
            hidden_from_continue=bool(progress.hidden_from_continue),
            min_seconds=min_seconds,
            signals=signals,
        )
        ts = progress.last_watched_at.timestamp() if progress.last_watched_at else 0.0

        if progress.movie_id is not None:
            movie = movies.get(progress.movie_id)
            if movie is None:
                continue
            profile.watched_movie_ids.add(movie.id)
            if progress.completed or float(progress.progress_percent or 0) >= 90:
                profile.completed_movie_ids.add(movie.id)
            if progress.hidden_from_continue:
                profile.dismissed_movie_ids.add(movie.id)
            elif (
                not progress.completed
                and float(progress.position_seconds or 0) >= min_seconds
                and float(progress.progress_percent or 0) < 90
            ):
                profile.continue_watching_movie_ids.add(movie.id)
            # Because-You-Watched anchors: meaningful progress only (not short/dismissed).
            if (
                strength >= float(signals.continue_watching)
                and not progress.hidden_from_continue
                and movie_is_public(movie)
            ):
                seed_candidates.append(("movie", movie.id, movie.title, strength, ts))
            type_w["movie"] += max(strength, 0)
            for g in movie.genre_links or []:
                genre_w[_norm(g.name)] += strength
            _add_weight(lang_w, movie.language, strength)
            for dub in movie.dubbed or []:
                if isinstance(dub, str):
                    _add_weight(dub_w, dub, strength * 0.6)
            for sub in movie.subtitles or []:
                if isinstance(sub, str):
                    _add_weight(sub_w, sub, strength * 0.5)
            _add_weight(country_w, movie.country, strength * 0.7)
            if movie.duration_minutes:
                runtimes.append(int(movie.duration_minutes))
            if movie.release_year:
                years.append(int(movie.release_year))
            for mcredit in movie_cast.get(movie.id, []):
                _add_weight(actor_w, mcredit.name, strength * 0.8)
                _add_id_weight(actor_id_w, mcredit.tmdb_person_id, strength * 0.8)
            for name in (movie.cast or [])[:6]:
                if isinstance(name, str):
                    _add_weight(actor_w, name, strength * 0.5)
        elif progress.episode_id is not None:
            episode = episodes.get(progress.episode_id)
            series = series_map.get(episode.series_id) if episode else None
            if series is None:
                continue
            profile.watched_series_ids.add(series.id)
            if progress.completed or float(progress.progress_percent or 0) >= 90:
                profile.completed_series_ids.add(series.id)
            if progress.hidden_from_continue:
                profile.dismissed_series_ids.add(series.id)
            elif (
                not progress.completed
                and float(progress.position_seconds or 0) >= min_seconds
                and float(progress.progress_percent or 0) < 90
            ):
                profile.continue_watching_series_ids.add(series.id)
            if (
                strength >= float(signals.continue_watching)
                and not progress.hidden_from_continue
                and series_is_public(series)
            ):
                seed_candidates.append(("series", series.id, series.title, strength, ts))
            type_w["series"] += max(strength, 0)
            for g in series.genre_links or []:
                genre_w[_norm(g.name)] += strength
            _add_weight(lang_w, series.language, strength)
            for dub in series.dubbed or []:
                if isinstance(dub, str):
                    _add_weight(dub_w, dub, strength * 0.6)
            for sub in series.subtitles or []:
                if isinstance(sub, str):
                    _add_weight(sub_w, sub, strength * 0.5)
            _add_weight(country_w, series.country, strength * 0.7)
            if series.release_year:
                years.append(int(series.release_year))
            for series_credit in series_cast.get(series.id, []):
                _add_weight(actor_w, series_credit.name, strength * 0.8)
                _add_id_weight(actor_id_w, series_credit.tmdb_person_id, strength * 0.8)

    # Watchlist medium positive signal.
    wl_rows = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.subscriber_id == subscriber.id)
        .order_by(WatchlistItem.created_at.desc())
        .limit(100)
        .all()
    )
    wl_movie_ids = {r.movie_id for r in wl_rows if r.movie_id}
    wl_series_ids = {r.series_id for r in wl_rows if r.series_id}
    wl_movies = {
        m.id: m
        for m in (
            db.query(Movie)
            .options(selectinload(Movie.genre_links))
            .filter(Movie.id.in_(wl_movie_ids))
            .all()
            if wl_movie_ids
            else []
        )
    }
    wl_series = {
        s.id: s
        for s in (
            db.query(Series)
            .options(selectinload(Series.genre_links))
            .filter(Series.id.in_(wl_series_ids))
            .all()
            if wl_series_ids
            else []
        )
    }
    w = float(signals.watchlist)
    for wl_item in wl_rows:
        if wl_item.movie_id is not None:
            movie = wl_movies.get(wl_item.movie_id)
            if movie is None:
                continue
            profile.watchlisted_movie_ids.add(movie.id)
            type_w["movie"] += w
            for g in movie.genre_links or []:
                genre_w[_norm(g.name)] += w
            _add_weight(lang_w, movie.language, w)
            _add_weight(country_w, movie.country, w * 0.5)
        elif wl_item.series_id is not None:
            series = wl_series.get(wl_item.series_id)
            if series is None:
                continue
            profile.watchlisted_series_ids.add(series.id)
            type_w["series"] += w
            for g in series.genre_links or []:
                genre_w[_norm(g.name)] += w
            _add_weight(lang_w, series.language, w)
            _add_weight(country_w, series.country, w * 0.5)

    profile.preferred_genres = _top_n(dict(genre_w), 16)
    profile.preferred_content_types = _top_n(dict(type_w), 4)
    profile.preferred_languages = _top_n(dict(lang_w), 10)
    profile.preferred_dubbed_languages = _top_n(dict(dub_w), 8)
    profile.preferred_subtitle_languages = _top_n(dict(sub_w), 8)
    profile.preferred_countries = _top_n(dict(country_w), 10)
    profile.preferred_actors = _top_n(dict(actor_w), 20)
    profile.preferred_actor_ids = {
        k: round(v, 4)
        for k, v in sorted(actor_id_w.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
        if v > 0
    }
    if runtimes:
        runtimes_sorted = sorted(runtimes)
        profile.preferred_runtime_min = max(1, runtimes_sorted[0] - 15)
        profile.preferred_runtime_max = runtimes_sorted[-1] + 20
    if years:
        years_sorted = sorted(years)
        profile.preferred_year_min = max(1900, years_sorted[0] - 5)
        profile.preferred_year_max = years_sorted[-1] + 2

    # Deduplicate seeds by content, keep strongest recent.
    best_seed: dict[tuple[str, int], tuple[str, float, float]] = {}
    for kind, cid, title, strength, ts in seed_candidates:
        key = (kind, cid)
        prev = best_seed.get(key)
        if prev is None or (strength, ts) > (prev[1], prev[2]):
            best_seed[key] = (title, strength, ts)
    seeds: list[tuple[str, int, str, float]] = [
        (kind, cid, title, strength)
        for (kind, cid), (title, strength, _ts) in sorted(
            best_seed.items(), key=lambda item: (-item[1][1], -item[1][2], item[0][0], item[0][1])
        )
    ]
    profile.seed_titles = [
        (k, i, t, s)  # type: ignore[misc]
        for k, i, t, s in seeds[:8]
    ]
    profile.has_personal_signals = bool(
        profile.preferred_genres
        or profile.watched_movie_ids
        or profile.watched_series_ids
        or profile.watchlisted_movie_ids
        or profile.watchlisted_series_ids
    )
    return profile


def profile_public_summary(profile: PreferenceProfile) -> dict:
    """Safe summary for admin debug (no session/auth data)."""
    return {
        "subscriber_id": profile.subscriber_id,
        "has_personal_signals": profile.has_personal_signals,
        "preferred_genres": profile.preferred_genres,
        "preferred_content_types": profile.preferred_content_types,
        "preferred_languages": profile.preferred_languages,
        "preferred_dubbed_languages": profile.preferred_dubbed_languages,
        "preferred_subtitle_languages": profile.preferred_subtitle_languages,
        "preferred_countries": profile.preferred_countries,
        "preferred_actors": list(profile.preferred_actors.keys())[:12],
        "preferred_runtime_range": [profile.preferred_runtime_min, profile.preferred_runtime_max],
        "preferred_year_range": [profile.preferred_year_min, profile.preferred_year_max],
        "watched_movie_count": len(profile.watched_movie_ids),
        "watched_series_count": len(profile.watched_series_ids),
        "watchlist_movie_count": len(profile.watchlisted_movie_ids),
        "watchlist_series_count": len(profile.watchlisted_series_ids),
        "dismissed_movie_count": len(profile.dismissed_movie_ids),
        "completed_movie_count": len(profile.completed_movie_ids),
        "continue_watching_movie_count": len(profile.continue_watching_movie_ids),
        "watchlist_excluded_from_recommended": True,
        "seed_titles": [
            {"content_type": k, "id": i, "title": t, "strength": round(s, 3)}
            for k, i, t, s in profile.seed_titles[:5]
        ],
    }
