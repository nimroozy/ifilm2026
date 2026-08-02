"""Remove only demo-owned data. Never deletes real users or content."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

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

    def summary_lines(self) -> list[str]:
        return [
            "Demo cleanup dry-run summary (demo-owned only):",
            f"  admins: {len(self.admin_usernames)} {self.admin_usernames}",
            f"  admin_roles: {len(self.admin_role_names)} {self.admin_role_names}",
            f"  subscribers: {len(self.subscriber_usernames)} {self.subscriber_usernames}",
            f"  genres_created: {len(self.genre_ids)} {self.genre_ids}",
            f"  movies: {len(self.movie_ids)}",
            f"  series: {len(self.series_ids)}",
            f"  seasons: {len(self.season_ids)}",
            f"  episodes: {len(self.episode_ids)}",
            f"  media_assets: {len(self.media_asset_ids)}",
            f"  packages: {len(self.package_ids)}",
            f"  artwork_files: {len(self.artwork_files)}",
            f"  watch_progress: {len(self.watch_progress_ids)}",
        ]


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

    # Discover demo-prefixed catalog when ownership file is partial.
    if not plan.movie_ids:
        plan.movie_ids = [
            m.id for m in db.query(Movie).filter(Movie.slug.like("demo-%")).all()
        ]
    if not plan.series_ids:
        plan.series_ids = [
            s.id for s in db.query(Series).filter(Series.slug.like("demo-%")).all()
        ]
    if plan.series_ids and not plan.season_ids:
        plan.season_ids = [
            s.id for s in db.query(Season).filter(Season.series_id.in_(plan.series_ids)).all()
        ]
    if plan.season_ids and not plan.episode_ids:
        plan.episode_ids = [
            e.id for e in db.query(Episode).filter(Episode.season_id.in_(plan.season_ids)).all()
        ]

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
    return plan


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
        if path.is_file() and "demo-" in path.name:
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
