"""Seed a realistic TMDB-backed demo catalog."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.bootstrap import seed_encoding_profiles
from app.core.config import Settings
from app.models.content import Episode, Movie, Season, Series
from app.services.demo.media import count_active_demo_packages, demo_work_dir, upload_and_encode
from app.services.demo.ownership import DemoOwnership, load_ownership, save_ownership, utcnow_iso
from app.services.demo.seed import (
    _apply_status_path,
    _commit_sha,
    _pick_actor,
    _publish_entity,
    _seed_admins,
    _seed_subscribers,
    _write_credentials,
)
from app.services.demo.settings_store import mark_demo_installed
from app.services.tmdb.client import TMDBClient
from app.services.tmdb.curated import CURATED_MOVIES, CURATED_SERIES, REAL_DEMO_SEED_VERSION
from app.services.tmdb.import_service import import_movie, import_series

logger = logging.getLogger(__name__)


@dataclass
class RealSeedReport:
    seed_version: str = REAL_DEMO_SEED_VERSION
    commit_sha: str = ""
    users_added: int = 0
    movies: int = 0
    series: int = 0
    seasons: int = 0
    episodes: int = 0
    media_assets: int = 0
    active_hls_packages: int = 0
    published_items: int = 0
    credentials_path: str = ""
    deviations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "seed_version": self.seed_version,
            "commit_sha": self.commit_sha,
            "users_added": self.users_added,
            "movies": self.movies,
            "series": self.series,
            "seasons": self.seasons,
            "episodes": self.episodes,
            "media_assets": self.media_assets,
            "active_hls_packages": self.active_hls_packages,
            "published_items": self.published_items,
            "credentials_path": self.credentials_path,
            "deviations": list(self.deviations),
        }


def _track_unique(values: list, items) -> None:
    seen = set(values)
    for item in items:
        if item not in seen:
            values.append(item)
            seen.add(item)


def _apply_movie_status(db: Session, movie: Movie, target: str, actor, report: RealSeedReport) -> None:
    if target == "published":
        _publish_entity(db, "movie", movie.id, actor, report, movie.slug)
    else:
        _apply_status_path(db, entity_type="movie", entity_id=movie.id, path=target, actor=actor)


def _apply_series_mode(db: Session, series: Series, mode: str, actor, report: RealSeedReport) -> None:
    seasons = (
        db.query(Season)
        .filter(Season.series_id == series.id)
        .order_by(Season.season_number)
        .all()
    )
    if mode == "draft":
        return
    if mode == "fully_published":
        for season in seasons:
            for episode in (
                db.query(Episode)
                .filter(Episode.season_id == season.id)
                .order_by(Episode.episode_number)
                .all()
            ):
                _publish_entity(db, "episode", episode.id, actor, report, series.slug)
            _publish_entity(db, "season", season.id, actor, report, series.slug)
        _publish_entity(db, "series", series.id, actor, report, series.slug)
        return
    if mode == "partial" and seasons:
        first = seasons[0]
        episodes = (
            db.query(Episode)
            .filter(Episode.season_id == first.id)
            .order_by(Episode.episode_number)
            .all()
        )
        for episode in episodes[:2]:
            _publish_entity(db, "episode", episode.id, actor, report, series.slug)
        if len(episodes) >= 3:
            _apply_status_path(db, entity_type="episode", entity_id=episodes[2].id, path="in_review", actor=actor)
        _publish_entity(db, "season", first.id, actor, report, series.slug)
        _publish_entity(db, "series", series.id, actor, report, series.slug)


def _attach_movie_clip(
    db: Session,
    settings: Settings,
    ownership: DemoOwnership,
    movie: Movie,
    actor,
    report: RealSeedReport,
) -> None:
    try:
        upload_and_encode(
            db,
            settings=settings,
            admin=actor,
            ownership=ownership,
            work_dir=demo_work_dir(settings),
            label=f"tmdb-demo-clip-movie-{movie.tmdb_id}",
            movie_id=movie.id,
            duration_seconds=20,
        )
        movie.has_demo_clip = True
        db.add(movie)
        db.flush()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        report.deviations.append(f"Demo Clip media failed for movie {movie.tmdb_id}: {exc}")
        logger.exception("Demo Clip media failed for movie %s", movie.tmdb_id)


def _attach_episode_clips(
    db: Session,
    settings: Settings,
    ownership: DemoOwnership,
    series: Series,
    actor,
    report: RealSeedReport,
    limit: int,
) -> None:
    if limit <= 0:
        return
    episodes = (
        db.query(Episode)
        .filter(Episode.series_id == series.id)
        .order_by(Episode.season_id, Episode.episode_number)
        .limit(limit)
        .all()
    )
    for episode in episodes:
        try:
            upload_and_encode(
                db,
                settings=settings,
                admin=actor,
                ownership=ownership,
                work_dir=demo_work_dir(settings),
                label=f"tmdb-demo-clip-episode-{episode.tmdb_id or episode.id}",
                episode_id=episode.id,
                duration_seconds=22,
            )
            episode.has_demo_clip = True
            db.add(episode)
            db.flush()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            report.deviations.append(f"Demo Clip media failed for episode {episode.id}: {exc}")
            logger.exception("Demo Clip media failed for episode %s", episode.id)


def _merge_write_credentials(path: Path, rows: list[tuple[str, str, str]]) -> None:
    if not rows:
        return
    existing: dict[tuple[str, str], str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                existing[(parts[0], parts[1])] = parts[2]
    for kind, username, password in rows:
        existing[(kind, username)] = password
    merged = [(kind, username, password) for (kind, username), password in sorted(existing.items())]
    _write_credentials(path, merged)


def seed_real_demo(
    db: Session,
    settings: Settings,
    *,
    credentials_path: Path | None = None,
    skip_media: bool = False,
    client: TMDBClient | None = None,
) -> RealSeedReport:
    if not settings.tmdb_enabled:
        raise RuntimeError("TMDB_ENABLED must be true to seed the real demo catalog")
    report = RealSeedReport(commit_sha=_commit_sha())
    ownership = load_ownership(settings)
    if not ownership.installed_at:
        ownership.installed_at = utcnow_iso()
    ownership.seed_version = REAL_DEMO_SEED_VERSION
    ownership.commit_sha = report.commit_sha

    seed_encoding_profiles(db)
    cred_rows: list[tuple[str, str, str]] = []
    report.users_added += _seed_admins(db, ownership, cred_rows)
    report.users_added += _seed_subscribers(db, settings, ownership, cred_rows)
    db.flush()
    actor = _pick_actor(db)
    client = client or TMDBClient(settings)

    for curated_movie in CURATED_MOVIES:
        result = import_movie(
            db,
            settings,
            curated_movie.tmdb_id,
            client=client,
            demo_owned=True,
            seed_version=REAL_DEMO_SEED_VERSION,
            force=True,
        )
        movie = db.get(Movie, result.entity_id)
        if movie is None:
            continue
        _track_unique(ownership.movie_ids, [movie.id])
        _track_unique(ownership.movie_slugs, [movie.slug])
        _track_unique(ownership.artwork_files, result.artwork_files)
        if curated_movie.with_demo_clip and not skip_media:
            _attach_movie_clip(db, settings, ownership, movie, actor, report)
        if curated_movie.featured or curated_movie.trending:
            movie.is_featured = bool(curated_movie.featured)
            movie.is_trending = bool(curated_movie.trending)
            db.add(movie)
            db.flush()
        try:
            _apply_movie_status(db, movie, curated_movie.status, actor, report)
        except Exception as exc:  # noqa: BLE001
            report.deviations.append(f"Movie status failed for TMDB {curated_movie.tmdb_id}: {exc}")
            logger.exception("Movie status failed for TMDB %s", curated_movie.tmdb_id)

    for curated_series in CURATED_SERIES:
        result = import_series(
            db,
            settings,
            curated_series.tmdb_id,
            client=client,
            demo_owned=True,
            seed_version=REAL_DEMO_SEED_VERSION,
            force=True,
            seasons_limit=curated_series.seasons,
            episodes_per_season=curated_series.episodes_per_season,
        )
        series = db.get(Series, result.entity_id)
        if series is None:
            continue
        _track_unique(ownership.series_ids, [series.id])
        _track_unique(ownership.series_slugs, [series.slug])
        _track_unique(ownership.season_ids, result.season_ids)
        _track_unique(ownership.episode_ids, result.episode_ids)
        _track_unique(ownership.artwork_files, result.artwork_files)
        if curated_series.featured or curated_series.trending:
            series.is_featured = bool(curated_series.featured)
            series.is_trending = bool(curated_series.trending)
            db.add(series)
            db.flush()
        if not skip_media:
            _attach_episode_clips(db, settings, ownership, series, actor, report, curated_series.with_demo_clips)
        try:
            _apply_series_mode(db, series, curated_series.mode, actor, report)
        except Exception as exc:  # noqa: BLE001
            report.deviations.append(f"Series mode failed for TMDB {curated_series.tmdb_id}: {exc}")
            logger.exception("Series mode failed for TMDB %s", curated_series.tmdb_id)

    mark_demo_installed(
        db,
        version=REAL_DEMO_SEED_VERSION,
        commit_sha=report.commit_sha,
        installed_at=ownership.installed_at,
    )
    db.commit()
    save_ownership(settings, ownership)

    cred_path = credentials_path or Path(settings.artwork_root) / ".demo" / "credentials.txt"
    _merge_write_credentials(cred_path, cred_rows)
    report.credentials_path = str(cred_path)

    report.movies = len(set(ownership.movie_ids))
    report.series = len(set(ownership.series_ids))
    report.seasons = len(set(ownership.season_ids))
    report.episodes = len(set(ownership.episode_ids))
    report.media_assets = len(set(ownership.media_asset_ids))
    report.active_hls_packages = count_active_demo_packages(db, ownership)
    report.published_items = (
        db.query(Movie).filter(Movie.id.in_(ownership.movie_ids or [0]), Movie.status == "published").count()
        + db.query(Series).filter(Series.id.in_(ownership.series_ids or [0]), Series.status == "published").count()
        + db.query(Episode).filter(Episode.id.in_(ownership.episode_ids or [0]), Episode.status == "published").count()
    )
    if skip_media:
        report.deviations.append("skip_media=1: no synthetic Demo Clip media generated")
    return report
