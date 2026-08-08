"""Fetch and store TMDB translations for movies/series/episodes without overwriting manual text."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.content import Episode, Movie, Season, Series
from app.services.content_i18n import store_tmdb_locale_bundle
from app.services.tmdb.client import TMDBClient
from app.services.tmdb.import_service import _short_description, _translation


@dataclass
class TranslationsSyncResult:
    entity_type: str
    entity_id: int
    tmdb_id: int | None
    locales_written: list[str] = field(default_factory=list)
    fields_written: int = 0
    skipped_manual: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "tmdb_id": self.tmdb_id,
            "locales_written": self.locales_written,
            "fields_written": self.fields_written,
            "skipped_manual": self.skipped_manual,
            "notes": self.notes,
        }


def _bundle_from_translation_data(data: dict[str, Any], *, title_key: str) -> dict[str, str]:
    title = str(data.get(title_key) or data.get("title") or data.get("name") or "").strip()
    overview = str(data.get("overview") or "").strip()
    tagline = str(data.get("tagline") or "").strip()
    out: dict[str, str] = {}
    if title:
        out["title"] = title
    if overview:
        out["overview"] = overview
        out["description"] = overview
        out["short_description"] = _short_description(overview)
    if tagline:
        out["tagline"] = tagline
    return out


def sync_movie_translations(
    db: Session,
    *,
    settings: Settings,
    movie: Movie,
    client: TMDBClient | None = None,
    commit: bool = True,
) -> TranslationsSyncResult:
    result = TranslationsSyncResult(entity_type="movie", entity_id=movie.id, tmdb_id=movie.tmdb_id)
    if not movie.tmdb_id:
        result.notes.append("movie_has_no_tmdb_id")
        return result
    client = client or TMDBClient(settings)
    details = client.movie_details(int(movie.tmdb_id), language="en-US")

    # English from primary payload + translations block
    en_data = {
        "title": str(details.get("title") or movie.title or ""),
        "overview": str(details.get("overview") or ""),
        "tagline": str(details.get("tagline") or ""),
    }
    en_bundle = _bundle_from_translation_data(en_data, title_key="title")
    written = store_tmdb_locale_bundle(
        db, entity_type="movie", entity_id=movie.id, locale="en", fields=en_bundle
    )
    if written:
        result.locales_written.append("en")
        result.fields_written += written

    fa_data = _translation(details, "fa")
    fa_bundle = _bundle_from_translation_data(fa_data, title_key="title")
    if fa_bundle:
        written = store_tmdb_locale_bundle(
            db, entity_type="movie", entity_id=movie.id, locale="fa", fields=fa_bundle
        )
        if written:
            result.locales_written.append("fa")
            result.fields_written += written
    else:
        result.notes.append("no_fa_translation_on_tmdb")

    # Do not invent Pashto from Persian — only store ps when TMDB provides ps (rare).
    ps_data = _translation(details, "ps")
    ps_bundle = _bundle_from_translation_data(ps_data, title_key="title")
    if ps_bundle:
        written = store_tmdb_locale_bundle(
            db, entity_type="movie", entity_id=movie.id, locale="ps", fields=ps_bundle
        )
        if written:
            result.locales_written.append("ps")
            result.fields_written += written

    if commit:
        db.commit()
    else:
        db.flush()
    return result


def sync_series_translations(
    db: Session,
    *,
    settings: Settings,
    series: Series,
    client: TMDBClient | None = None,
    include_episodes: bool = True,
    commit: bool = True,
) -> TranslationsSyncResult:
    result = TranslationsSyncResult(entity_type="series", entity_id=series.id, tmdb_id=series.tmdb_id)
    if not series.tmdb_id:
        result.notes.append("series_has_no_tmdb_id")
        return result
    client = client or TMDBClient(settings)
    details = client.tv_details(int(series.tmdb_id), language="en-US")

    en_data = {
        "title": str(details.get("name") or series.title or ""),
        "overview": str(details.get("overview") or ""),
        "tagline": str(details.get("tagline") or ""),
    }
    en_bundle = _bundle_from_translation_data(en_data, title_key="title")
    written = store_tmdb_locale_bundle(
        db, entity_type="series", entity_id=series.id, locale="en", fields=en_bundle
    )
    if written:
        result.locales_written.append("en")
        result.fields_written += written

    fa_data = _translation(details, "fa")
    # TV translations use "name" in data
    if fa_data and not fa_data.get("title") and fa_data.get("name"):
        fa_data = {**fa_data, "title": fa_data.get("name")}
    fa_bundle = _bundle_from_translation_data(fa_data, title_key="title")
    if fa_bundle:
        written = store_tmdb_locale_bundle(
            db, entity_type="series", entity_id=series.id, locale="fa", fields=fa_bundle
        )
        if written:
            result.locales_written.append("fa")
            result.fields_written += written

    if include_episodes and series.tmdb_id:
        seasons = (
            db.query(Season)
            .filter(Season.series_id == series.id, Season.deleted_at.is_(None))
            .all()
        )
        for season in seasons:
            if season.season_number is None:
                continue
            try:
                season_details = client.season_details(
                    int(series.tmdb_id), int(season.season_number), language="en-US"
                )
            except Exception:  # noqa: BLE001
                continue
            for item in season_details.get("episodes") or []:
                if not isinstance(item, dict):
                    continue
                ep_num = item.get("episode_number")
                if ep_num is None:
                    continue
                episode = (
                    db.query(Episode)
                    .filter(
                        Episode.season_id == season.id,
                        Episode.episode_number == int(ep_num),
                        Episode.deleted_at.is_(None),
                    )
                    .first()
                )
                if episode is None:
                    continue
                ep_en = {
                    "title": str(item.get("name") or ""),
                    "overview": str(item.get("overview") or ""),
                }
                written = store_tmdb_locale_bundle(
                    db,
                    entity_type="episode",
                    entity_id=episode.id,
                    locale="en",
                    fields=_bundle_from_translation_data(ep_en, title_key="title"),
                )
                result.fields_written += written
            # Persian season request for episode overviews when available
            try:
                season_fa = client.season_details(
                    int(series.tmdb_id), int(season.season_number), language="fa-IR"
                )
            except Exception:  # noqa: BLE001
                season_fa = {}
            for item in season_fa.get("episodes") or []:
                if not isinstance(item, dict):
                    continue
                ep_num = item.get("episode_number")
                if ep_num is None:
                    continue
                episode = (
                    db.query(Episode)
                    .filter(
                        Episode.season_id == season.id,
                        Episode.episode_number == int(ep_num),
                        Episode.deleted_at.is_(None),
                    )
                    .first()
                )
                if episode is None:
                    continue
                ep_fa = {
                    "title": str(item.get("name") or ""),
                    "overview": str(item.get("overview") or ""),
                }
                bundle = _bundle_from_translation_data(ep_fa, title_key="title")
                if not bundle:
                    continue
                written = store_tmdb_locale_bundle(
                    db,
                    entity_type="episode",
                    entity_id=episode.id,
                    locale="fa",
                    fields=bundle,
                )
                result.fields_written += written

    if commit:
        db.commit()
    else:
        db.flush()
    return result
