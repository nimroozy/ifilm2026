"""Configurable recommendation scoring weights and signal strengths."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class ScoreWeights:
    genre: float = 0.30
    history: float = 0.20
    cast: float = 0.15
    collection: float = 0.10
    language: float = 0.10
    recency: float = 0.05
    popularity: float = 0.10

    def normalized(self) -> ScoreWeights:
        total = (
            self.genre
            + self.history
            + self.cast
            + self.collection
            + self.language
            + self.recency
            + self.popularity
        )
        if total <= 0:
            return ScoreWeights()
        return ScoreWeights(
            genre=self.genre / total,
            history=self.history / total,
            cast=self.cast / total,
            collection=self.collection / total,
            language=self.language / total,
            recency=self.recency / total,
            popularity=self.popularity / total,
        )


@dataclass(frozen=True)
class SignalWeights:
    """Relative preference-signal strengths when building a user profile."""

    completed: float = 1.0
    watched_high: float = 0.9  # >70%
    watched_medium: float = 0.55  # 30–70%
    watchlist: float = 0.5
    continue_watching: float = 0.45
    dismissed: float = -0.35
    very_short: float = 0.05  # near-neutral


def score_weights_from_settings(settings: Settings | None = None) -> ScoreWeights:
    settings = settings or get_settings()
    return ScoreWeights(
        genre=float(getattr(settings, "rec_weight_genre", 0.30)),
        history=float(getattr(settings, "rec_weight_history", 0.20)),
        cast=float(getattr(settings, "rec_weight_cast", 0.15)),
        collection=float(getattr(settings, "rec_weight_collection", 0.10)),
        language=float(getattr(settings, "rec_weight_language", 0.10)),
        recency=float(getattr(settings, "rec_weight_recency", 0.05)),
        popularity=float(getattr(settings, "rec_weight_popularity", 0.10)),
    ).normalized()


def signal_weights_from_settings(settings: Settings | None = None) -> SignalWeights:
    settings = settings or get_settings()
    return SignalWeights(
        completed=float(getattr(settings, "rec_signal_completed", 1.0)),
        watched_high=float(getattr(settings, "rec_signal_watched_high", 0.9)),
        watched_medium=float(getattr(settings, "rec_signal_watched_medium", 0.55)),
        watchlist=float(getattr(settings, "rec_signal_watchlist", 0.5)),
        continue_watching=float(getattr(settings, "rec_signal_continue_watching", 0.45)),
        dismissed=float(getattr(settings, "rec_signal_dismissed", -0.35)),
        very_short=float(getattr(settings, "rec_signal_very_short", 0.05)),
    )


# Minimum quality threshold for a "Because You Watched" shelf.
BECAUSE_MIN_CANDIDATES = 3
BECAUSE_MIN_TOP_SCORE = 0.28

# Bounded candidate pool sizes (performance).
CANDIDATE_GENRE_LIMIT = 80
CANDIDATE_POPULAR_LIMIT = 40
CANDIDATE_RECENT_LIMIT = 40
CANDIDATE_COLLECTION_LIMIT = 40
CANDIDATE_CAST_LIMIT = 40
CANDIDATE_TOTAL_CAP = 220

# Short-lived per-user recommendation cache TTL (seconds).
CACHE_TTL_SECONDS = 45
