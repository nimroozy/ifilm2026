"""Authoritative public catalog visibility policy."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.content import Episode, Movie, Season, Series
from app.models.enums import PUBLIC_VISIBLE_STATUSES


def is_publicly_visible_entity(entity) -> bool:
    """True when a single catalog row is itself published and not soft-deleted."""
    if entity is None:
        return False
    if getattr(entity, "deleted_at", None) is not None:
        return False
    return getattr(entity, "status", None) in PUBLIC_VISIBLE_STATUSES


def apply_public_visibility(query, model):
    """Filter a SQLAlchemy query to publicly visible catalog rows."""
    return query.filter(model.deleted_at.is_(None), model.status == "published")


def movie_is_public(movie: Movie) -> bool:
    return is_publicly_visible_entity(movie)


def series_is_public(series: Series) -> bool:
    return is_publicly_visible_entity(series)


def season_is_public(db: Session, season: Season) -> bool:
    """Season is structural: public only when season + parent series are published."""
    if not is_publicly_visible_entity(season):
        return False
    series = db.get(Series, season.series_id)
    return is_publicly_visible_entity(series)


def episode_is_public(db: Session, episode: Episode) -> bool:
    """Episode public when episode + season + series are all published and not deleted."""
    if not is_publicly_visible_entity(episode):
        return False
    season = db.get(Season, episode.season_id) if episode.season_id else None
    series = db.get(Series, episode.series_id) if episode.series_id else None
    if not is_publicly_visible_entity(season):
        return False
    if not is_publicly_visible_entity(series):
        return False
    return True


def public_season_count(series: Series) -> int:
    return len(
        [
            s
            for s in (series.seasons or [])
            if s.deleted_at is None and s.status == "published"
        ]
    )


def public_episode_count_for_series(series: Series) -> int:
    total = 0
    for season in series.seasons or []:
        if season.deleted_at is not None or season.status != "published":
            continue
        total += len(
            [e for e in (season.episodes or []) if e.deleted_at is None and e.status == "published"]
        )
    return total


def public_episode_count_for_season(season: Season) -> int:
    return len(
        [e for e in (season.episodes or []) if e.deleted_at is None and e.status == "published"]
    )
