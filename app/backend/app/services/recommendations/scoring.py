"""Explainable recommendation scoring over catalog feature rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.services.recommendations.types import PreferenceProfile, ScoredCandidate
from app.services.recommendations.weights import ScoreWeights, score_weights_from_settings


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


@dataclass
class CatalogFeature:
    kind: str  # movie | series
    id: int
    title: str
    slug: str
    poster_url: str
    backdrop_url: str
    release_year: int | None
    imdb_rating: float | None
    genres: list[str]
    genre_slugs: list[str]
    language: str
    dubbed: list[str]
    subtitles: list[str]
    country: str
    duration_minutes: int | None
    views: int
    published_at_ts: float
    cast_names: set[str]
    cast_ids: set[int]
    collection_ids: set[int]
    playable: bool = False
    collection_overlap: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.id}"


def score_candidate(
    feature: CatalogFeature,
    profile: PreferenceProfile,
    *,
    weights: ScoreWeights | None = None,
    exclude_ids: set[tuple[str, int]] | None = None,
    similar_to_title: str | None = None,
    now_ts: float | None = None,
) -> ScoredCandidate | None:
    weights = weights or score_weights_from_settings()
    key = (feature.kind, feature.id)
    if exclude_ids and key in exclude_ids:
        return None

    # Skip already strongly engaged items from personalized lists.
    if feature.kind == "movie" and feature.id in profile.watched_movie_ids:
        if feature.id in profile.completed_movie_ids:
            return None
    if feature.kind == "series" and feature.id in profile.completed_series_ids:
        return None

    genre_score = 0.0
    genre_hits: list[str] = []
    if profile.preferred_genres and feature.genres:
        pref_total = sum(max(v, 0) for v in profile.preferred_genres.values()) or 1.0
        hit = 0.0
        for g in feature.genres:
            w = profile.preferred_genres.get(_norm(g), 0.0)
            if w > 0:
                hit += w
                genre_hits.append(g)
        genre_score = min(1.0, hit / pref_total * 2.0)

    history_score = 0.0
    history_reasons: list[str] = []
    if similar_to_title:
        history_score = max(history_score, 0.85)
        history_reasons.append(f"Similar to {similar_to_title}")
    # Overlap with genres of completed titles already baked into genre_score;
    # boost if this exact title is watchlisted (rare once excluded from Recommended).
    if feature.kind == "movie" and feature.id in profile.watchlisted_movie_ids:
        history_score = max(history_score, 0.4)
    if feature.kind == "series" and feature.id in profile.watchlisted_series_ids:
        history_score = max(history_score, 0.4)
    # NOTE: preferred_content_types (movie vs series) must NOT inflate history_score.
    # That previously made every movie look like a "taste" match for movie-heavy users.

    cast_score = 0.0
    cast_hits: list[str] = []
    if profile.preferred_actor_ids and feature.cast_ids:
        overlap_ids = profile.preferred_actor_ids.keys() & feature.cast_ids
        if overlap_ids:
            cast_score = min(1.0, len(overlap_ids) / 3.0)
            # Resolve display names from feature cast names when possible.
            cast_hits = sorted(n for n in feature.cast_names if _norm(n) in profile.preferred_actors)[:2]
    if cast_score == 0 and profile.preferred_actors and feature.cast_names:
        overlap = {_norm(n) for n in feature.cast_names} & set(profile.preferred_actors)
        if overlap:
            cast_score = min(1.0, len(overlap) / 3.0)
            cast_hits = sorted(overlap)[:2]

    collection_score = 0.0
    # Collection overlap is scored when candidate shares collections with seeds;
    # engine injects via feature.collection_ids relative to seed collections when set.
    # Here: if user has watchlisted items in same collection, feature carries membership;
    # a non-empty collection_ids with profile signals yields a mild boost when seed collections
    # were stamped onto the feature by the engine (see engine._annotate_collection_overlap).
    if feature.collection_overlap > 0:
        collection_score = min(1.0, float(feature.collection_overlap))

    language_score = 0.0
    lang_hit = ""
    cand_lang = _norm(feature.language)
    if cand_lang and cand_lang in profile.preferred_languages:
        language_score = min(1.0, profile.preferred_languages[cand_lang])
        lang_hit = feature.language
    else:
        for dub in feature.dubbed:
            d = _norm(dub)
            if d in profile.preferred_dubbed_languages or d in profile.preferred_languages:
                language_score = max(language_score, 0.7)
                lang_hit = dub
                break
        for sub in feature.subtitles:
            s = _norm(sub)
            if s in profile.preferred_subtitle_languages:
                language_score = max(language_score, 0.45)
                break
    if profile.preferred_countries and _norm(feature.country) in profile.preferred_countries:
        language_score = max(language_score, 0.55)

    # Recency: published within ~2 years scores higher.
    now = now_ts if now_ts is not None else datetime.now(UTC).timestamp()
    recency_score = 0.0
    if feature.published_at_ts > 0:
        age_days = max(0.0, (now - feature.published_at_ts) / 86400.0)
        if age_days <= 30:
            recency_score = 1.0
        elif age_days <= 180:
            recency_score = 0.7
        elif age_days <= 730:
            recency_score = 0.4
        else:
            recency_score = 0.15
    elif feature.release_year:
        age = max(0, datetime.now(UTC).year - feature.release_year)
        recency_score = 1.0 if age <= 2 else 0.5 if age <= 8 else 0.2

    # Popularity / rating blend.
    views = max(0, int(feature.views or 0))
    view_part = min(1.0, views / 5000.0)
    rating = float(feature.imdb_rating or 0.0)
    rating_part = min(1.0, max(0.0, rating / 10.0))
    popularity_score = 0.55 * view_part + 0.45 * rating_part

    # Mild negative for dismissed genre-heavy items: downrank, not hard exclude.
    dismiss_penalty = 0.0
    if feature.kind == "movie" and feature.id in profile.dismissed_movie_ids:
        dismiss_penalty = 0.25
    if feature.kind == "series" and feature.id in profile.dismissed_series_ids:
        dismiss_penalty = 0.25
    if dismiss_penalty == 0 and profile.dismissed_movie_ids and genre_hits:
        # Soft penalty when genres overlap heavily with dismissed content preferences —
        # applied only when candidate genres match top preferred that were also dismissed
        # (approximated by negative genre weights already reducing genre_score).
        pass

    # Taste signal for personalized filtering: genre/cast/collection + meaningful history.
    # Excludes language / popularity / recency so Popular padding cannot masquerade.
    taste = genre_score + cast_score + collection_score
    if history_score > 0 and (similar_to_title or history_reasons):
        taste += history_score
    components = {
        "genre": round(genre_score, 4),
        "history": round(history_score, 4),
        "cast": round(cast_score, 4),
        "collection": round(collection_score, 4),
        "language": round(language_score, 4),
        "recency": round(recency_score, 4),
        "popularity": round(popularity_score, 4),
        "taste": round(taste, 4),
    }
    raw = (
        weights.genre * genre_score
        + weights.history * history_score
        + weights.cast * cast_score
        + weights.collection * collection_score
        + weights.language * language_score
        + weights.recency * recency_score
        + weights.popularity * popularity_score
    )
    score = max(0.0, min(1.0, raw - dismiss_penalty))

    reasons: list[str] = []
    if genre_hits:
        # Prefer display casing from feature genres.
        display = genre_hits[0]
        reasons.append(f"Matches your preferred {display} genre")
    reasons.extend(history_reasons)
    if cast_hits:
        actor = cast_hits[0].title() if cast_hits[0].islower() else cast_hits[0]
        reasons.append("Features an actor from movies you completed")
        if actor and actor.lower() not in " ".join(reasons).lower():
            reasons[-1] = f"Features {actor}, an actor from titles you enjoyed"
    if collection_score >= 0.4:
        reasons.append("From a collection related to titles you watch")
    if lang_hit:
        reasons.append(f"Matches your language preference ({lang_hit})")
    if popularity_score >= 0.65 and len(reasons) < 3:
        reasons.append("Popular in the catalog")
    if recency_score >= 0.7 and len(reasons) < 3:
        reasons.append("Recently added")
    if dismiss_penalty > 0 and score > 0:
        # Do not advertise dismiss penalty in public reasons.
        pass
    if not reasons and score >= 0.2:
        reasons.append("A good match from our catalog")

    return ScoredCandidate(
        kind=feature.kind,  # type: ignore[arg-type]
        id=feature.id,
        title=feature.title,
        slug=feature.slug,
        poster_url=feature.poster_url or "",
        backdrop_url=feature.backdrop_url or "",
        release_year=feature.release_year,
        imdb_rating=feature.imdb_rating,
        genres=list(feature.genres),
        language=feature.language or "",
        country=feature.country or "",
        duration_minutes=feature.duration_minutes,
        views=feature.views,
        published_at_ts=feature.published_at_ts,
        score=round(score, 4),
        reasons=reasons[:4],
        components=components,
        playable=feature.playable,
    )


def stable_sort_key(item: ScoredCandidate) -> tuple:
    """Deterministic ordering: score desc, rating desc, id desc, kind."""
    rating = float(item.imdb_rating or 0.0)
    return (-item.score, -rating, -item.id, item.kind)


def short_explanation(reasons: list[str]) -> str | None:
    if not reasons:
        return None
    first = reasons[0]
    # Compact card copy.
    if first.startswith("Matches your preferred ") and first.endswith(" genre"):
        genre = first[len("Matches your preferred ") : -len(" genre")]
        return f"Because you enjoy {genre}"
    if first.startswith("Similar to "):
        return first
    if first.startswith("Features "):
        return "Because of actors you like"
    return first
