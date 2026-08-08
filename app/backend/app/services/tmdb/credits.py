"""Parse and persist TMDB cast credits (never fetched on every public page load)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.content import Movie, Series
from app.models.credits import MovieCastCredit, SeriesCastCredit
from app.services.tmdb.artwork import build_image_url
from app.services.tmdb.client import TMDBClient

MediaType = Literal["movie", "series"]
MAX_CAST = 24


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_cast_entries(credits_payload: dict[str, Any], *, limit: int = MAX_CAST) -> list[dict[str, Any]]:
    cast = credits_payload.get("cast") if isinstance(credits_payload, dict) else None
    if not isinstance(cast, list):
        return []
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in cast:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        if raw_id is None:
            continue
        try:
            person_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if person_id in seen:
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        seen.add(person_id)
        raw_order = item.get("order")
        try:
            order = int(raw_order) if raw_order is not None else len(rows)
        except (TypeError, ValueError):
            order = len(rows)
        profile_path = str(item.get("profile_path") or "").strip()
        rows.append(
            {
                "tmdb_person_id": person_id,
                "name": name[:255],
                "character_name": str(item.get("character") or "").strip()[:255],
                "profile_path": profile_path[:512],
                "credit_order": order,
            }
        )
        if len(rows) >= limit:
            break
    rows.sort(key=lambda r: (r["credit_order"], r["name"]))
    return rows


def _profile_url(settings: Settings, profile_path: str) -> str:
    if not profile_path:
        return ""
    try:
        return build_image_url(settings, profile_path, size="w185")
    except Exception:  # noqa: BLE001
        return ""


def replace_movie_credits(
    db: Session,
    settings: Settings,
    movie: Movie,
    credits_payload: dict[str, Any],
) -> int:
    entries = parse_cast_entries(credits_payload)
    db.query(MovieCastCredit).filter(MovieCastCredit.movie_id == movie.id).delete(synchronize_session=False)
    now = utcnow()
    for entry in entries:
        db.add(
            MovieCastCredit(
                movie_id=movie.id,
                tmdb_person_id=entry["tmdb_person_id"],
                name=entry["name"],
                character_name=entry["character_name"],
                profile_path=entry["profile_path"],
                profile_url=_profile_url(settings, entry["profile_path"]),
                credit_order=entry["credit_order"],
                created_at=now,
                updated_at=now,
            )
        )
    movie.credits_synced_at = now
    # Keep legacy name-only cast JSON in sync for older clients.
    movie.cast = [e["name"] for e in entries]
    db.add(movie)
    db.flush()
    return len(entries)


def replace_series_credits(
    db: Session,
    settings: Settings,
    series: Series,
    credits_payload: dict[str, Any],
) -> int:
    entries = parse_cast_entries(credits_payload)
    db.query(SeriesCastCredit).filter(SeriesCastCredit.series_id == series.id).delete(synchronize_session=False)
    now = utcnow()
    for entry in entries:
        db.add(
            SeriesCastCredit(
                series_id=series.id,
                tmdb_person_id=entry["tmdb_person_id"],
                name=entry["name"],
                character_name=entry["character_name"],
                profile_path=entry["profile_path"],
                profile_url=_profile_url(settings, entry["profile_path"]),
                credit_order=entry["credit_order"],
                created_at=now,
                updated_at=now,
            )
        )
    series.credits_synced_at = now
    db.add(series)
    db.flush()
    return len(entries)


def sync_movie_credits(
    db: Session,
    settings: Settings,
    movie: Movie,
    *,
    client: TMDBClient | None = None,
) -> int:
    if not movie.tmdb_id:
        return 0
    client = client or TMDBClient(settings)
    payload = client.movie_credits(int(movie.tmdb_id))
    return replace_movie_credits(db, settings, movie, payload)


def sync_series_credits(
    db: Session,
    settings: Settings,
    series: Series,
    *,
    client: TMDBClient | None = None,
) -> int:
    if not series.tmdb_id:
        return 0
    client = client or TMDBClient(settings)
    payload = client.tv_credits(int(series.tmdb_id))
    return replace_series_credits(db, settings, series, payload)


def list_movie_credits(db: Session, movie_id: int) -> list[MovieCastCredit]:
    return (
        db.query(MovieCastCredit)
        .filter(MovieCastCredit.movie_id == movie_id)
        .order_by(MovieCastCredit.credit_order.asc(), MovieCastCredit.id.asc())
        .all()
    )


def list_series_credits(db: Session, series_id: int) -> list[SeriesCastCredit]:
    return (
        db.query(SeriesCastCredit)
        .filter(SeriesCastCredit.series_id == series_id)
        .order_by(SeriesCastCredit.credit_order.asc(), SeriesCastCredit.id.asc())
        .all()
    )
