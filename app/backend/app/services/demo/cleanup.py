"""Remove only demo-owned data. Never deletes real users or content."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.admin import AdminRole, AdminUser
from app.models.content import Episode, Genre, Movie, Season, Series
from app.models.media_assets import MediaAsset, UploadSession
from app.models.media_encoding import MediaPackage, MediaRendition
from app.models.media_playback import MediaPlaybackSession
from app.models.media_processing import MediaProcessingJob, MediaProcessingJobEvent
from app.models.publication import MediaPublicationEvent
from app.models.subscriber_auth import (
    SubscriberDeviceSession,
    SubscriberEntitlementSnapshot,
    SubscriberRefreshToken,
)
from app.models.user import Subscriber
from app.models.watch_progress import UserWatchProgress
from app.services.demo.constants import ADMIN_FIXTURES, PROVIDER_DEMO, SUBSCRIBER_FIXTURES
from app.services.demo.ownership import clear_ownership_file, load_ownership
from app.services.demo.settings_store import clear_demo_markers
from app.services.storage import media_root


@dataclass
class CleanupPlan:
    admin_usernames: list[str] = field(default_factory=list)
    admin_role_names: list[str] = field(default_factory=list)
    subscriber_usernames: list[str] = field(default_factory=list)
    genre_ids: list[int] = field(default_factory=list)
    movie_ids: list[int] = field(default_factory=list)
    series_ids: list[int] = field(default_factory=list)
    season_ids: list[int] = field(default_factory=list)
    episode_ids: list[int] = field(default_factory=list)
    media_asset_ids: list[str] = field(default_factory=list)
    package_ids: list[str] = field(default_factory=list)
    artwork_files: list[str] = field(default_factory=list)
    media_files: list[str] = field(default_factory=list)
    watch_progress_ids: list[int] = field(default_factory=list)
    publication_event_ids: list[int] = field(default_factory=list)
    movie_titles: list[str] = field(default_factory=list)
    series_titles: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [
            "Demo cleanup dry-run summary (demo-owned only):",
            f"  admins: {len(self.admin_usernames)} {self.admin_usernames}",
            f"  admin_roles: {len(self.admin_role_names)} {self.admin_role_names}",
            f"  subscribers: {len(self.subscriber_usernames)} {self.subscriber_usernames}",
            f"  genres_created: {len(self.genre_ids)} {self.genre_ids}",
            f"  movies: {len(self.movie_ids)}",
        ]
        for title in self.movie_titles[:40]:
            lines.append(f"    - movie: {title}")
        if len(self.movie_titles) > 40:
            lines.append(f"    … {len(self.movie_titles) - 40} more movies")
        lines.append(f"  series: {len(self.series_ids)}")
        for title in self.series_titles[:40]:
            lines.append(f"    - series: {title}")
        if len(self.series_titles) > 40:
            lines.append(f"    … {len(self.series_titles) - 40} more series")
        lines.extend(
            [
                f"  seasons: {len(self.season_ids)}",
                f"  episodes: {len(self.episode_ids)}",
                f"  media_assets: {len(self.media_asset_ids)}",
                f"  packages: {len(self.package_ids)}",
                f"  artwork_files: {len(self.artwork_files)}",
                f"  media_files: {len(self.media_files)}",
                f"  watch_progress: {len(self.watch_progress_ids)}",
                f"  publication_events: {len(self.publication_event_ids)}",
            ]
        )
        return lines


def build_cleanup_plan(db: Session, settings: Settings) -> CleanupPlan:
    ownership = load_ownership(settings)
    plan = CleanupPlan(
        admin_usernames=list(ownership.admin_usernames)
        or [f["username"] for f in ADMIN_FIXTURES],
        admin_role_names=list(ownership.admin_role_names)
        or [f["role_name"] for f in ADMIN_FIXTURES],
        subscriber_usernames=list(ownership.subscriber_usernames)
        or [f["username"] for f in SUBSCRIBER_FIXTURES],
        genre_ids=list(ownership.genre_ids_created),
        movie_ids=list(ownership.movie_ids),
        series_ids=list(ownership.series_ids),
        season_ids=list(ownership.season_ids),
        episode_ids=list(ownership.episode_ids),
        media_asset_ids=list(ownership.media_asset_ids),
        package_ids=list(ownership.package_ids),
        artwork_files=list(ownership.artwork_files),
        media_files=list(ownership.media_files),
        watch_progress_ids=list(ownership.watch_progress_ids),
    )

    # Discover TMDB/demo-owned catalog when ownership file is partial.
    # Never treat demo-* slugs alone as deletable: production may keep former
    # fake-demo rows with demo_owned=False as real catalog content.
    discovered_movies = [m.id for m in db.query(Movie).filter(Movie.demo_owned.is_(True)).all()]
    plan.movie_ids = sorted(set(plan.movie_ids + discovered_movies))
    discovered_series = [s.id for s in db.query(Series).filter(Series.demo_owned.is_(True)).all()]
    plan.series_ids = sorted(set(plan.series_ids + discovered_series))
    discovered_episodes = [e.id for e in db.query(Episode).filter(Episode.demo_owned.is_(True)).all()]
    plan.episode_ids = sorted(set(plan.episode_ids + discovered_episodes))

    # Hard safety rail: ownership.json from older seeds may still list IDs that
    # were later marked non-demo. Never delete those rows or their dependents.
    _restrict_plan_to_demo_owned(db, plan)

    plan.artwork_files = sorted(set(plan.artwork_files + _discover_demo_artwork_files(db, plan)))

    # Only delete subscribers that are demo provider / known fixtures.
    safe_subs: list[str] = []
    for username in plan.subscriber_usernames:
        subscriber = db.query(Subscriber).filter(Subscriber.username == username).one_or_none()
        if subscriber is None:
            continue
        if subscriber.identity_provider == PROVIDER_DEMO or username.startswith("demo_"):
            safe_subs.append(username)
    plan.subscriber_usernames = safe_subs

    safe_admins: list[str] = []
    for username in plan.admin_usernames:
        admin = db.query(AdminUser).filter(AdminUser.username == username).one_or_none()
        if admin is None:
            continue
        if (admin.email or "").endswith("@ifilm.demo") or username in {
            f["username"] for f in ADMIN_FIXTURES
        }:
            safe_admins.append(username)
    plan.admin_usernames = safe_admins

    if plan.movie_ids:
        movies = db.query(Movie).filter(Movie.id.in_(plan.movie_ids)).order_by(Movie.id).all()
        plan.movie_titles = [
            f"{m.title} (id={m.id}, tmdb={m.tmdb_id}, demo_owned={bool(m.demo_owned)}, slug={m.slug})"
            for m in movies
        ]
        if any(not bool(m.demo_owned) for m in movies):
            raise RuntimeError("Cleanup plan refused: non-demo movie listed for deletion")
    if plan.series_ids:
        series_rows = db.query(Series).filter(Series.id.in_(plan.series_ids)).order_by(Series.id).all()
        plan.series_titles = [
            f"{s.title} (id={s.id}, tmdb={s.tmdb_id}, demo_owned={bool(s.demo_owned)}, slug={s.slug})"
            for s in series_rows
        ]
        if any(not bool(s.demo_owned) for s in series_rows):
            raise RuntimeError("Cleanup plan refused: non-demo series listed for deletion")

    # Publication events tied to demo catalog entities (dry-run visibility).
    pub_ids: list[int] = []
    if plan.movie_ids:
        pub_ids.extend(
            e.id
            for e in db.query(MediaPublicationEvent)
            .filter(
                MediaPublicationEvent.entity_type == "movie",
                MediaPublicationEvent.entity_id.in_(plan.movie_ids),
            )
            .all()
        )
    if plan.series_ids:
        pub_ids.extend(
            e.id
            for e in db.query(MediaPublicationEvent)
            .filter(
                MediaPublicationEvent.entity_type == "series",
                MediaPublicationEvent.entity_id.in_(plan.series_ids),
            )
            .all()
        )
    if plan.season_ids:
        pub_ids.extend(
            e.id
            for e in db.query(MediaPublicationEvent)
            .filter(
                MediaPublicationEvent.entity_type == "season",
                MediaPublicationEvent.entity_id.in_(plan.season_ids),
            )
            .all()
        )
    if plan.episode_ids:
        pub_ids.extend(
            e.id
            for e in db.query(MediaPublicationEvent)
            .filter(
                MediaPublicationEvent.entity_type == "episode",
                MediaPublicationEvent.entity_id.in_(plan.episode_ids),
            )
            .all()
        )
    plan.publication_event_ids = sorted(set(pub_ids))
    return plan


def _restrict_plan_to_demo_owned(db: Session, plan: CleanupPlan) -> None:
    """Drop any catalog/media targets that are not demo-owned.

    Older ownership.json files and demo-* slugs may still point at rows that
    operators intentionally kept (demo_owned=False). Those must never be deleted.
    """
    demo_movie_ids = {row[0] for row in db.query(Movie.id).filter(Movie.demo_owned.is_(True)).all()}
    demo_series_ids = {
        row[0] for row in db.query(Series.id).filter(Series.demo_owned.is_(True)).all()
    }

    plan.movie_ids = sorted(set(plan.movie_ids) & demo_movie_ids)
    plan.series_ids = sorted(set(plan.series_ids) & demo_series_ids)

    if plan.series_ids:
        plan.season_ids = sorted(
            row[0]
            for row in db.query(Season.id).filter(Season.series_id.in_(plan.series_ids)).all()
        )
        plan.episode_ids = sorted(
            row[0]
            for row in db.query(Episode.id).filter(Episode.season_id.in_(plan.season_ids)).all()
        )
    else:
        plan.season_ids = []
        plan.episode_ids = sorted(
            row[0]
            for row in db.query(Episode.id)
            .filter(Episode.id.in_(plan.episode_ids or [0]), Episode.demo_owned.is_(True))
            .all()
        )

    preserved_movie_ids = {
        row[0] for row in db.query(Movie.id).filter(Movie.demo_owned.is_(False)).all()
    }
    preserved_series_ids = {
        row[0] for row in db.query(Series.id).filter(Series.demo_owned.is_(False)).all()
    }
    preserved_episode_ids = {
        row[0]
        for row in db.query(Episode.id)
        .filter(
            (Episode.demo_owned.is_(False))
            | (Episode.series_id.in_(preserved_series_ids or [-1]))
        )
        .all()
    }
    deletable_movie_ids = set(plan.movie_ids)
    deletable_episode_ids = set(plan.episode_ids)

    safe_asset_ids: list[str] = []
    if plan.media_asset_ids:
        for asset in db.query(MediaAsset).filter(MediaAsset.id.in_(plan.media_asset_ids)).all():
            if asset.movie_id is not None:
                if asset.movie_id in preserved_movie_ids or asset.movie_id not in deletable_movie_ids:
                    continue
            if asset.series_id is not None and asset.series_id in preserved_series_ids:
                continue
            if asset.episode_id is not None:
                if (
                    asset.episode_id in preserved_episode_ids
                    or asset.episode_id not in deletable_episode_ids
                ):
                    continue
            # Keep unattached ownership assets only when not linked to preserved rows.
            if (
                asset.movie_id is None
                and asset.episode_id is None
                and asset.series_id is not None
                and asset.series_id not in set(plan.series_ids)
            ):
                continue
            safe_asset_ids.append(asset.id)
    plan.media_asset_ids = sorted(set(safe_asset_ids))

    if plan.package_ids and plan.media_asset_ids:
        plan.package_ids = sorted(
            row[0]
            for row in db.query(MediaPackage.id)
            .filter(
                MediaPackage.id.in_(plan.package_ids),
                MediaPackage.media_asset_id.in_(plan.media_asset_ids),
            )
            .all()
        )
    else:
        plan.package_ids = []

    # Ownership path lists often include preserved fake-demo artwork/media.
    # Rebuild artwork from remaining demo-owned entities; keep only demo-seed media paths
    # that are not tied to preserved movie/series slugs.
    plan.artwork_files = []
    preserved_slugs = {
        row[0]
        for row in db.query(Movie.slug).filter(Movie.demo_owned.is_(False)).all()
    } | {
        row[0]
        for row in db.query(Series.slug).filter(Series.demo_owned.is_(False)).all()
    }
    filtered_media: list[str] = []
    for path in plan.media_files:
        name = Path(path).name
        if any(slug and slug in name for slug in preserved_slugs):
            continue
        if "demo-seed" in path or "/temp/demo" in path:
            filtered_media.append(path)
    plan.media_files = filtered_media

    if plan.watch_progress_ids:
        plan.watch_progress_ids = sorted(
            row[0]
            for row in db.query(UserWatchProgress.id)
            .filter(UserWatchProgress.id.in_(plan.watch_progress_ids))
            .filter(
                (
                    UserWatchProgress.movie_id.isnot(None)
                    & UserWatchProgress.movie_id.in_(deletable_movie_ids or [-1])
                )
                | (
                    UserWatchProgress.episode_id.isnot(None)
                    & UserWatchProgress.episode_id.in_(deletable_episode_ids or [-1])
                )
            )
            .all()
        )


def _artwork_relative_from_url(value: str) -> str:
    if not value:
        return ""
    if value.startswith("/artwork/"):
        return value[len("/artwork/") :]
    parsed = urlparse(value)
    marker = "/artwork/"
    if marker in parsed.path:
        return parsed.path.split(marker, 1)[1]
    return ""


def _discover_demo_artwork_files(db: Session, plan: CleanupPlan) -> list[str]:
    files: list[str] = []
    for movie in db.query(Movie).filter(Movie.id.in_(plan.movie_ids or [0])).all():
        for value in (movie.poster_url, movie.backdrop_url, getattr(movie, "logo_url", "")):
            rel = _artwork_relative_from_url(value or "")
            if rel and ("demo-" in rel or "tmdb-" in rel):
                files.append(rel)
    for series in db.query(Series).filter(Series.id.in_(plan.series_ids or [0])).all():
        for value in (series.poster_url, series.backdrop_url, getattr(series, "logo_url", "")):
            rel = _artwork_relative_from_url(value or "")
            if rel and ("demo-" in rel or "tmdb-" in rel):
                files.append(rel)
    for episode in db.query(Episode).filter(Episode.id.in_(plan.episode_ids or [0])).all():
        rel = _artwork_relative_from_url(episode.thumbnail_url or "")
        if rel and ("demo-" in rel or "tmdb-" in rel):
            files.append(rel)
    return files


def execute_cleanup(db: Session, settings: Settings, plan: CleanupPlan) -> None:
    # Watch progress
    if plan.watch_progress_ids:
        db.query(UserWatchProgress).filter(UserWatchProgress.id.in_(plan.watch_progress_ids)).delete(
            synchronize_session=False
        )
    if plan.subscriber_usernames:
        sub_ids = [
            s.id
            for s in db.query(Subscriber).filter(Subscriber.username.in_(plan.subscriber_usernames))
        ]
        if sub_ids:
            db.query(UserWatchProgress).filter(UserWatchProgress.subscriber_id.in_(sub_ids)).delete(
                synchronize_session=False
            )
            db.query(SubscriberRefreshToken).filter(
                SubscriberRefreshToken.subscriber_id.in_(sub_ids)
            ).delete(synchronize_session=False)
            db.query(SubscriberDeviceSession).filter(
                SubscriberDeviceSession.subscriber_id.in_(sub_ids)
            ).delete(synchronize_session=False)
            db.query(SubscriberEntitlementSnapshot).filter(
                SubscriberEntitlementSnapshot.subscriber_id.in_(sub_ids)
            ).delete(synchronize_session=False)
            db.query(Subscriber).filter(Subscriber.id.in_(sub_ids)).delete(synchronize_session=False)

    # Playback sessions for demo assets
    if plan.media_asset_ids:
        db.query(MediaPlaybackSession).filter(
            MediaPlaybackSession.media_asset_id.in_(plan.media_asset_ids)
        ).delete(synchronize_session=False)
        job_ids = [
            j.id
            for j in db.query(MediaProcessingJob)
            .filter(MediaProcessingJob.media_asset_id.in_(plan.media_asset_ids))
            .all()
        ]
        if job_ids:
            db.query(MediaProcessingJobEvent).filter(
                MediaProcessingJobEvent.job_id.in_(job_ids)
            ).delete(synchronize_session=False)
            db.query(MediaProcessingJob).filter(MediaProcessingJob.id.in_(job_ids)).delete(
                synchronize_session=False
            )
        db.query(UploadSession).filter(UploadSession.media_asset_id.in_(plan.media_asset_ids)).delete(
            synchronize_session=False
        )

    if plan.package_ids:
        db.query(MediaRendition).filter(MediaRendition.package_id.in_(plan.package_ids)).delete(
            synchronize_session=False
        )
        db.query(MediaPackage).filter(MediaPackage.id.in_(plan.package_ids)).delete(
            synchronize_session=False
        )

    if plan.media_asset_ids:
        db.query(MediaAsset).filter(MediaAsset.id.in_(plan.media_asset_ids)).delete(
            synchronize_session=False
        )

    # Publication events for demo entities
    for entity_type, ids in (
        ("movie", plan.movie_ids),
        ("series", plan.series_ids),
        ("season", plan.season_ids),
        ("episode", plan.episode_ids),
    ):
        if ids:
            db.query(MediaPublicationEvent).filter(
                MediaPublicationEvent.entity_type == entity_type,
                MediaPublicationEvent.entity_id.in_(ids),
            ).delete(synchronize_session=False)

    if plan.episode_ids:
        db.query(Episode).filter(Episode.id.in_(plan.episode_ids)).delete(synchronize_session=False)
    if plan.season_ids:
        db.query(Season).filter(Season.id.in_(plan.season_ids)).delete(synchronize_session=False)
    if plan.series_ids:
        db.query(Series).filter(Series.id.in_(plan.series_ids)).delete(synchronize_session=False)
    if plan.movie_ids:
        db.query(Movie).filter(Movie.id.in_(plan.movie_ids)).delete(synchronize_session=False)

    # Genres only if we created them and they are unused
    for genre_id in plan.genre_ids:
        genre = db.get(Genre, genre_id)
        if genre is None:
            continue
        in_movies = db.query(Movie).join(Movie.genre_links).filter(Genre.id == genre_id).count()
        in_series = db.query(Series).join(Series.genre_links).filter(Genre.id == genre_id).count()
        if in_movies == 0 and in_series == 0:
            db.delete(genre)

    if plan.admin_usernames:
        db.query(AdminUser).filter(AdminUser.username.in_(plan.admin_usernames)).delete(
            synchronize_session=False
        )
    for role_name in plan.admin_role_names:
        role = db.query(AdminRole).filter(AdminRole.name == role_name).one_or_none()
        if role is None:
            continue
        still_used = db.query(AdminUser).filter(AdminUser.role_id == role.id).count()
        if still_used == 0:
            db.delete(role)

    clear_demo_markers(db)
    db.commit()

    # Filesystem cleanup (demo artwork + generated media paths)
    art_root = Path(settings.artwork_root)
    for rel in plan.artwork_files:
        path = art_root / rel
        if path.is_file() and ("demo-" in path.name or "tmdb-" in path.name):
            path.unlink(missing_ok=True)

    root = media_root()
    for rel in plan.media_files:
        path = Path(rel)
        if not path.is_absolute():
            path = root / rel
        try:
            resolved = path.resolve()
            if resolved.is_file() and str(resolved).startswith(str(root.resolve())):
                if "demo" in resolved.name or resolved.suffix == ".mp4":
                    # Only delete files under originals/temp that belong to tracked assets.
                    if any(part in resolved.parts for part in ("originals", "temp", "demo-seed")):
                        resolved.unlink(missing_ok=True)
        except OSError:
            pass

    for package_id in plan.package_ids:
        pkg_dir = root / "packages" / package_id
        if pkg_dir.is_dir():
            shutil.rmtree(pkg_dir, ignore_errors=True)

    demo_temp = root / "temp" / "demo-seed"
    if demo_temp.is_dir():
        shutil.rmtree(demo_temp, ignore_errors=True)

    clear_ownership_file(settings)
    cred = art_root / ".demo" / "credentials.txt"
    if cred.is_file():
        cred.unlink(missing_ok=True)
