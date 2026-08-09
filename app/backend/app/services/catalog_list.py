"""Card/list serialization with batched lookups (no per-card N+1)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.content import Episode, Movie, Season, Series
from app.models.media_assets import MediaAsset
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage
from app.models.media_tracks import MediaTrack
from app.schemas.content import (
    AudioAvailabilityOut,
    EpisodeOut,
    LocalizationSourcesOut,
    MovieOut,
    SeriesOut,
    SubtitleAvailabilityOut,
)
from app.services.catalog import genre_out
from app.services.catalog_availability import (
    build_audio_availability,
    build_subtitle_availability,
)
from app.services.content_i18n import (
    load_translations_for_entities,
    localized_episode_fields,
    localized_movie_fields,
    localized_series_fields,
    normalize_locale,
)


def batch_active_package_asset_ids(db: Session, asset_ids: list[str]) -> set[str]:
    """Return asset ids that have an active completed HLS package (one query)."""
    if not asset_ids:
        return set()
    rows = (
        db.query(MediaPackage.media_asset_id)
        .filter(
            MediaPackage.media_asset_id.in_(list(dict.fromkeys(asset_ids))),
            MediaPackage.package_type == PACKAGE_TYPE_HLS_VOD,
            MediaPackage.status == "completed",
            MediaPackage.is_active.is_(True),
            MediaPackage.superseded_at.is_(None),
        )
        .all()
    )
    return {r[0] for r in rows}


def _playability_from_assets(
    *,
    movie: Movie,
    assets: list[MediaAsset],
    packaged_asset_ids: set[str],
) -> tuple[bool, bool, bool]:
    """Mirror content_playability using preloaded assets + package id set."""
    if not assets:
        return False, False, False
    for asset in assets:
        if asset.upload_status in {"failed", "cancelled", "deleted"}:
            continue
        if getattr(asset, "source_type", "uploaded") == "external":
            continue
        if getattr(asset, "deleted_at", None) is not None:
            continue
        if asset.id in packaged_asset_ids:
            return True, True, False
    for asset in assets:
        if asset.upload_status in {"failed", "cancelled", "deleted"}:
            continue
        if getattr(asset, "source_type", "uploaded") != "external":
            continue
        if not getattr(asset, "external_is_primary", False):
            continue
        if asset.external_url and asset.external_validated_at:
            demo = bool(getattr(movie, "demo_owned", False))
            return demo, False, True
        return False, False, False
    return False, False, False


def _playability_from_episode_assets(
    *,
    episode: Episode,
    series: Series | None,
    assets: list[MediaAsset],
    packaged_asset_ids: set[str],
) -> tuple[bool, bool, bool]:
    """Mirror content_playability for episodes using preloaded assets + package id set."""
    if not assets:
        return False, False, False
    for asset in assets:
        if asset.upload_status in {"failed", "cancelled", "deleted"}:
            continue
        if getattr(asset, "source_type", "uploaded") == "external":
            continue
        if getattr(asset, "deleted_at", None) is not None:
            continue
        if asset.id in packaged_asset_ids:
            return True, True, False
    for asset in assets:
        if asset.upload_status in {"failed", "cancelled", "deleted"}:
            continue
        if getattr(asset, "source_type", "uploaded") != "external":
            continue
        if not getattr(asset, "external_is_primary", False):
            continue
        if asset.external_url and asset.external_validated_at:
            demo = bool(getattr(episode, "demo_owned", False))
            if not demo and series is not None:
                demo = bool(getattr(series, "demo_owned", False))
            return demo, False, True
        return False, False, False
    return False, False, False


def _batch_episode_assets(db: Session, episode_ids: list[int]) -> dict[int, list[MediaAsset]]:
    if not episode_ids:
        return {}
    assets = (
        db.query(MediaAsset)
        .filter(MediaAsset.episode_id.in_(list(dict.fromkeys(episode_ids))))
        .order_by(MediaAsset.id.desc())
        .all()
    )
    by_episode: dict[int, list[MediaAsset]] = defaultdict(list)
    for asset in assets:
        if asset.episode_id is not None:
            by_episode[asset.episode_id].append(asset)
    return by_episode


def _batch_episode_packaged_tracks(
    db: Session, by_episode_assets: dict[int, list[MediaAsset]]
) -> dict[int, tuple[list[Any], list[Any]]]:
    """Return {episode_id: (audio_tracks, subtitle_tracks)} in one MediaTrack query."""
    if not by_episode_assets:
        return {}
    asset_to_episode: dict[str, int] = {}
    asset_ids: list[str] = []
    for episode_id, assets in by_episode_assets.items():
        # Match _packaged_tracks_for_episode: newest 20 assets per episode.
        for asset in assets[:20]:
            asset_to_episode[asset.id] = episode_id
            asset_ids.append(asset.id)
    if not asset_ids:
        return {eid: ([], []) for eid in by_episode_assets}
    rows = (
        db.query(MediaTrack)
        .filter(MediaTrack.media_asset_id.in_(list(dict.fromkeys(asset_ids))))
        .order_by(MediaTrack.sort_order.asc(), MediaTrack.id.asc())
        .all()
    )
    out: dict[int, tuple[list[Any], list[Any]]] = {
        eid: ([], []) for eid in by_episode_assets
    }
    for row in rows:
        mapped_episode_id = asset_to_episode.get(row.media_asset_id)
        if mapped_episode_id is None:
            continue
        audio, subs = out[mapped_episode_id]
        if row.track_type == "audio":
            audio.append(row)
        elif row.track_type == "subtitle":
            subs.append(row)
    return out


def episodes_list_out(
    db: Session,
    episodes: list[Episode],
    *,
    series: Series | None = None,
    locale: str | None = None,
) -> list[EpisodeOut]:
    """Serialize season/public episode lists with batched playability/tracks/i18n."""
    if not episodes:
        return []
    loc = normalize_locale(locale)
    episode_ids = [e.id for e in episodes]
    tr_map = load_translations_for_entities(db, entity_type="episode", entity_ids=episode_ids)
    by_episode = _batch_episode_assets(db, episode_ids)
    packaged = batch_active_package_asset_ids(
        db, [a.id for rows in by_episode.values() for a in rows]
    )
    tracks_by_episode = _batch_episode_packaged_tracks(db, by_episode)

    # Resolve series once when callers pass None (avoid per-episode db.get).
    series_by_id: dict[int, Series] = {}
    if series is not None:
        series_by_id[series.id] = series
    else:
        missing_series_ids = sorted(
            {
                e.series_id
                for e in episodes
                if e.series_id
                and getattr(e, "series", None) is None
            }
        )
        if missing_series_ids:
            for row in db.query(Series).filter(Series.id.in_(missing_series_ids)).all():
                series_by_id[row.id] = row

    results: list[EpisodeOut] = []
    for episode in episodes:
        ep_series = (
            series
            if series is not None and series.id == episode.series_id
            else getattr(episode, "series", None) or series_by_id.get(episode.series_id)
        )
        assets = by_episode.get(episode.id, [])
        playable, has_package, has_external = _playability_from_episode_assets(
            episode=episode,
            series=ep_series,
            assets=assets,
            packaged_asset_ids=packaged,
        )
        preferred = [a for a in assets if (a.category or "") == "originals"] or assets
        probe_json = None
        audio_count = None
        sub_count = None
        if preferred:
            asset = preferred[0]
            for candidate in preferred:
                if candidate.probe_json or candidate.audio_stream_count is not None:
                    asset = candidate
                    break
            probe_json = asset.probe_json if isinstance(asset.probe_json, dict) else None
            audio_count = asset.audio_stream_count
            sub_count = asset.subtitle_stream_count
        packaged_audio, packaged_subs = tracks_by_episode.get(episode.id, ([], []))
        audio = build_audio_availability(
            language=getattr(ep_series, "language", None) if ep_series is not None else None,
            spoken_languages=getattr(ep_series, "spoken_languages", None)
            if ep_series is not None
            else None,
            metadata_source=getattr(ep_series, "metadata_source", None)
            if ep_series is not None
            else None,
            admin_audio=getattr(ep_series, "audio", None) if ep_series is not None else None,
            admin_dubbed=getattr(ep_series, "dubbed", None) if ep_series is not None else None,
            probe_json=probe_json,
            audio_stream_count=audio_count,
            packaged_audio_tracks=packaged_audio,
        )
        subs = build_subtitle_availability(
            admin_subtitles=getattr(ep_series, "subtitles", None) if ep_series is not None else None,
            probe_json=probe_json,
            subtitle_stream_count=sub_count,
            packaged_subtitle_tracks=packaged_subs,
        )
        localized = localized_episode_fields(
            db, episode, loc, preloaded_rows=tr_map.get(episode.id, [])
        )
        results.append(
            EpisodeOut(
                id=episode.id,
                season_id=episode.season_id,
                series_id=episode.series_id,
                episode_number=episode.episode_number,
                tmdb_id=getattr(episode, "tmdb_id", None),
                metadata_source=getattr(episode, "metadata_source", "") or "",
                demo_owned=bool(getattr(episode, "demo_owned", False)),
                has_demo_clip=bool(getattr(episode, "has_demo_clip", False)),
                title=localized["title"],
                description=localized["description"],
                duration_minutes=episode.duration_minutes,
                release_date=episode.release_date,
                thumbnail_url=episode.thumbnail_url or "",
                status=episode.status,
                published_at=episode.published_at,
                scheduled_publish_at=getattr(episode, "scheduled_publish_at", None),
                created_at=episode.created_at,
                updated_at=episode.updated_at,
                hls_path=episode.hls_path,
                playable=playable,
                has_playable_package=has_package,
                has_external_media=has_external,
                audio_availability=AudioAvailabilityOut.model_validate(audio.model_dump()),
                subtitle_availability=SubtitleAvailabilityOut.model_validate(subs.model_dump()),
                season=episode.season.season_number if episode.season else None,
                episode=episode.episode_number,
                duration=episode.duration_minutes,
                thumbnail=episode.thumbnail_url or "",
            )
        )
    return results


def batch_movie_playability(db: Session, movies: list[Movie]) -> dict[int, tuple[bool, bool, bool]]:
    ids = [m.id for m in movies]
    if not ids:
        return {}
    assets = (
        db.query(MediaAsset)
        .filter(MediaAsset.movie_id.in_(ids))
        .order_by(MediaAsset.created_at.desc())
        .all()
    )
    by_movie: dict[int, list[MediaAsset]] = defaultdict(list)
    for asset in assets:
        if asset.movie_id is not None:
            by_movie[asset.movie_id].append(asset)
    packaged = batch_active_package_asset_ids(db, [a.id for a in assets])
    out: dict[int, tuple[bool, bool, bool]] = {}
    for movie in movies:
        out[movie.id] = _playability_from_assets(
            movie=movie,
            assets=by_movie.get(movie.id, []),
            packaged_asset_ids=packaged,
        )
    return out


def batch_primary_probes(
    db: Session, movie_ids: list[int]
) -> dict[int, tuple[dict[str, Any] | None, int | None, int | None]]:
    if not movie_ids:
        return {}
    assets = (
        db.query(MediaAsset)
        .filter(MediaAsset.movie_id.in_(movie_ids))
        .order_by(MediaAsset.id.desc())
        .all()
    )
    by_movie: dict[int, list[MediaAsset]] = defaultdict(list)
    for asset in assets:
        if asset.movie_id is not None:
            by_movie[asset.movie_id].append(asset)
    out: dict[int, tuple[dict[str, Any] | None, int | None, int | None]] = {}
    for mid in movie_ids:
        rows = by_movie.get(mid, [])
        if not rows:
            out[mid] = (None, None, None)
            continue
        preferred = [a for a in rows if (a.category or "") == "originals"] or rows
        asset = preferred[0]
        for candidate in preferred:
            if candidate.probe_json or candidate.audio_stream_count is not None:
                asset = candidate
                break
        out[mid] = (
            asset.probe_json if isinstance(asset.probe_json, dict) else None,
            asset.audio_stream_count,
            asset.subtitle_stream_count,
        )
    return out


def batch_series_public_counts(db: Session, series_ids: list[int]) -> dict[int, tuple[int, int]]:
    """Return {series_id: (season_count, episode_count)} without loading ORM graphs."""
    if not series_ids:
        return {}
    ids = list(dict.fromkeys(series_ids))
    season_counts: dict[int, int] = {
        int(series_id): int(count)
        for series_id, count in (
            db.query(Season.series_id, func.count(Season.id))
            .filter(
                Season.series_id.in_(ids),
                Season.deleted_at.is_(None),
                Season.status == "published",
            )
            .group_by(Season.series_id)
            .all()
        )
    }
    episode_counts: dict[int, int] = {
        int(series_id): int(count)
        for series_id, count in (
            db.query(Season.series_id, func.count(Episode.id))
            .join(Episode, Episode.season_id == Season.id)
            .filter(
                Season.series_id.in_(ids),
                Season.deleted_at.is_(None),
                Season.status == "published",
                Episode.deleted_at.is_(None),
                Episode.status == "published",
            )
            .group_by(Season.series_id)
            .all()
        )
    }
    return {sid: (int(season_counts.get(sid, 0)), int(episode_counts.get(sid, 0))) for sid in ids}


def _batch_movie_assets(db: Session, movie_ids: list[int]) -> dict[int, list[MediaAsset]]:
    if not movie_ids:
        return {}
    assets = (
        db.query(MediaAsset)
        .filter(MediaAsset.movie_id.in_(movie_ids))
        .order_by(MediaAsset.created_at.desc())
        .all()
    )
    by_movie: dict[int, list[MediaAsset]] = defaultdict(list)
    for asset in assets:
        if asset.movie_id is not None:
            by_movie[asset.movie_id].append(asset)
    return by_movie


def movies_card_out(db: Session, movies: list[Movie], *, locale: str | None = None) -> list[MovieOut]:
    """Serialize movies for shelves/browse cards: batched i18n/playability, no cast credits."""
    if not movies:
        return []
    loc = normalize_locale(locale)
    movie_ids = [m.id for m in movies]
    tr_map = load_translations_for_entities(db, entity_type="movie", entity_ids=movie_ids)
    by_movie = _batch_movie_assets(db, movie_ids)
    packaged = batch_active_package_asset_ids(
        db, [a.id for rows in by_movie.values() for a in rows]
    )
    results: list[MovieOut] = []
    for movie in movies:
        genres = [genre_out(g, movie_count=0, series_count=0) for g in (movie.genre_links or [])]
        assets = by_movie.get(movie.id, [])
        playable, has_package, has_external = _playability_from_assets(
            movie=movie, assets=assets, packaged_asset_ids=packaged
        )
        preferred = [a for a in assets if (a.category or "") == "originals"] or assets
        probe_json = None
        audio_count = None
        sub_count = None
        if preferred:
            asset = preferred[0]
            for candidate in preferred:
                if candidate.probe_json or candidate.audio_stream_count is not None:
                    asset = candidate
                    break
            probe_json = asset.probe_json if isinstance(asset.probe_json, dict) else None
            audio_count = asset.audio_stream_count
            sub_count = asset.subtitle_stream_count
        audio = build_audio_availability(
            language=getattr(movie, "language", None),
            spoken_languages=getattr(movie, "spoken_languages", None),
            metadata_source=getattr(movie, "metadata_source", None),
            admin_audio=getattr(movie, "audio", None),
            admin_dubbed=getattr(movie, "dubbed", None),
            probe_json=probe_json,
            audio_stream_count=audio_count,
            has_playable_package=has_package,
            has_external_media=has_external,
        )
        subs = build_subtitle_availability(
            admin_subtitles=getattr(movie, "subtitles", None),
            probe_json=probe_json,
            subtitle_stream_count=sub_count,
        )
        localized = localized_movie_fields(
            db, movie, loc, preloaded_rows=tr_map.get(movie.id, [])
        )
        # Card payload: keep short synopsis only — no full overview, cast credits, or media packages.
        short = localized["short_description"] or localized["description"][:180]
        results.append(
            MovieOut(
                id=movie.id,
                title=localized["title"],
                original_title=movie.original_title or "",
                slug=movie.slug,
                description=short,
                short_description=short,
                tagline="",
                localization=LocalizationSourcesOut.model_validate(localized["localization"]),
                release_year=movie.release_year,
                release_date=movie.release_date,
                duration_minutes=movie.duration_minutes,
                age_rating=movie.age_rating or "",
                language=movie.language or "",
                country=movie.country or "",
                imdb_id=movie.imdb_id,
                imdb_rating=movie.imdb_rating,
                tmdb_id=getattr(movie, "tmdb_id", None),
                metadata_source=getattr(movie, "metadata_source", "") or "",
                demo_owned=bool(getattr(movie, "demo_owned", False)),
                poster_url=movie.poster_url or "",
                backdrop_url=movie.backdrop_url or "",
                logo_url=getattr(movie, "logo_url", "") or "",
                trailer_url="",
                spoken_languages=getattr(movie, "spoken_languages", None) or [],
                trailer_provider="",
                trailer_key="",
                trailer_title="",
                trailer_official=False,
                trailer_language="",
                trailer_published_at=None,
                has_demo_clip=bool(getattr(movie, "has_demo_clip", False)),
                status=movie.status,
                is_featured=bool(movie.is_featured),
                is_trending=bool(movie.is_trending),
                published_at=movie.published_at,
                scheduled_publish_at=getattr(movie, "scheduled_publish_at", None),
                created_at=movie.created_at,
                updated_at=movie.updated_at,
                genres=genres,
                director=movie.director or "",
                producer="",
                writer="",
                studio="",
                cast=[],
                credits=[],
                credits_synced_at=None,
                audio=movie.audio or [],
                subtitles=movie.subtitles or [],
                qualities=movie.qualities or [],
                dubbed=movie.dubbed or [],
                audio_availability=AudioAvailabilityOut.model_validate(audio.model_dump()),
                subtitle_availability=SubtitleAvailabilityOut.model_validate(subs.model_dump()),
                views=movie.views or 0,
                type="movie",
                hls_path=None,
                playable=playable,
                has_playable_package=has_package,
                has_external_media=has_external,
                year=movie.release_year,
                duration=movie.duration_minutes,
                rating=movie.imdb_rating,
                poster=movie.poster_url or "",
                backdrop=movie.backdrop_url or "",
                featured=bool(movie.is_featured),
            )
        )
    return results


def series_card_out(db: Session, series_items: list[Series], *, locale: str | None = None) -> list[SeriesOut]:
    if not series_items:
        return []
    loc = normalize_locale(locale)
    tr_map = load_translations_for_entities(
        db, entity_type="series", entity_ids=[s.id for s in series_items]
    )
    counts = batch_series_public_counts(db, [s.id for s in series_items])
    results: list[SeriesOut] = []
    for series in series_items:
        genres = [genre_out(g, movie_count=0, series_count=0) for g in (series.genre_links or [])]
        season_count, episode_count = counts.get(series.id, (0, 0))
        audio = build_audio_availability(
            language=getattr(series, "language", None),
            spoken_languages=getattr(series, "spoken_languages", None),
            metadata_source=getattr(series, "metadata_source", None),
            admin_audio=getattr(series, "audio", None),
            admin_dubbed=getattr(series, "dubbed", None),
            probe_json=None,
            audio_stream_count=None,
            has_playable_package=False,
            has_external_media=False,
        )
        subs = build_subtitle_availability(
            admin_subtitles=getattr(series, "subtitles", None),
            probe_json=None,
            subtitle_stream_count=None,
        )
        localized = localized_series_fields(
            db, series, loc, preloaded_rows=tr_map.get(series.id, [])
        )
        short = localized["short_description"] or localized["description"][:180]
        results.append(
            SeriesOut(
                id=series.id,
                title=localized["title"],
                original_title=series.original_title or "",
                slug=series.slug,
                description=short,
                short_description=short,
                tagline="",
                localization=LocalizationSourcesOut.model_validate(localized["localization"]),
                release_year=series.release_year,
                end_year=getattr(series, "end_year", None),
                age_rating=series.age_rating or "",
                language=series.language or "",
                country=series.country or "",
                imdb_id=series.imdb_id,
                imdb_rating=series.imdb_rating,
                tmdb_id=getattr(series, "tmdb_id", None),
                metadata_source=getattr(series, "metadata_source", "") or "",
                demo_owned=bool(getattr(series, "demo_owned", False)),
                poster_url=series.poster_url or "",
                backdrop_url=series.backdrop_url or "",
                logo_url=getattr(series, "logo_url", "") or "",
                trailer_url="",
                spoken_languages=getattr(series, "spoken_languages", None) or [],
                trailer_provider="",
                trailer_key="",
                trailer_title="",
                trailer_official=False,
                trailer_language="",
                trailer_published_at=None,
                has_demo_clip=bool(getattr(series, "has_demo_clip", False)),
                status=series.status,
                airing_status=series.airing_status or "Ongoing",
                is_featured=bool(series.is_featured),
                is_trending=bool(series.is_trending),
                published_at=series.published_at,
                scheduled_publish_at=getattr(series, "scheduled_publish_at", None),
                created_at=series.created_at,
                updated_at=series.updated_at,
                genres=genres,
                season_count=season_count,
                episode_count=episode_count,
                new_episode=bool(getattr(series, "new_episode", False)),
                audio=series.audio or [],
                subtitles=series.subtitles or [],
                dubbed=series.dubbed or [],
                audio_availability=AudioAvailabilityOut.model_validate(audio.model_dump()),
                subtitle_availability=SubtitleAvailabilityOut.model_validate(subs.model_dump()),
                credits=[],
                credits_synced_at=None,
                views=series.views or 0,
                type="series",
                year=series.release_year,
                seasons=season_count,
                episodes=episode_count,
                rating=series.imdb_rating,
                poster=series.poster_url or "",
                backdrop=series.backdrop_url or "",
                featured=bool(series.is_featured),
            )
        )
    return results
