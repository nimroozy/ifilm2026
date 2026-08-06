"""Remove only demo-owned data. Never deletes real users or content.

Data-retention rules
--------------------
- Non-demo catalog rows are never deleted.
- Admin accounts and admin roles are never deleted by cleanup.
- Publication/audit events for removed demo entities are retained as tombstones
  (sanitized metadata) so audit history stays intact.
- ``remove_fake_demo`` / ``real_demo_dry_run`` target synthetic/fake demo rows only
  (no TMDB id / non-tmdb metadata). Real TMDB demo catalog (v3) is retained.
- ``remove_demo`` may remove all ``demo_owned`` catalog rows (including TMDB),
  still without deleting admins or wiping publication history.
- Foreign keys are never disabled. No broad CASCADE is used.
"""

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
from app.services.demo.constants import (
    ADMIN_FIXTURES,
    PROVIDER_DEMO,
    SUBSCRIBER_FIXTURES,
)
from app.services.demo.ownership import (
    DemoOwnership,
    clear_ownership_file,
    load_ownership,
    save_ownership,
)
from app.services.demo.settings_store import clear_demo_markers, get_setting
from app.services.storage import media_root

# Constraint that previously failed production cleanup when admins were deleted:
# media_assets_created_by_admin_id_fkey → admin_users.id
ADMIN_MEDIA_FK_CONSTRAINT = "media_assets_created_by_admin_id_fkey"


@dataclass
class CleanupPlan:
    """Plan describing deletes, detaches, retains, and tombstones."""

    fake_only: bool = False
    # Deleted
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
    movie_titles: list[str] = field(default_factory=list)
    series_titles: list[str] = field(default_factory=list)
    # Detached (FK nulling only — never used to enable admin deletion)
    detached_media_asset_admin_refs: list[str] = field(default_factory=list)
    detached_package_admin_refs: list[str] = field(default_factory=list)
    # Retained
    retained_admin_usernames: list[str] = field(default_factory=list)
    retained_admin_role_names: list[str] = field(default_factory=list)
    retained_tmdb_movie_ids: list[int] = field(default_factory=list)
    retained_tmdb_series_ids: list[int] = field(default_factory=list)
    retained_nondemo_movie_ids: list[int] = field(default_factory=list)
    retained_nondemo_series_ids: list[int] = field(default_factory=list)
    # Audit tombstones (retained rows, sanitized)
    publication_event_ids: list[int] = field(default_factory=list)
    fk_dependent_notes: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        mode = "fake-demo only" if self.fake_only else "all demo-owned"
        lines = [
            f"Demo cleanup dry-run summary ({mode}):",
            "  DELETE:",
            f"    subscribers: {len(self.subscriber_usernames)} {self.subscriber_usernames}",
            f"    genres_unused: {len(self.genre_ids)} {self.genre_ids}",
            f"    movies: {len(self.movie_ids)}",
        ]
        for title in self.movie_titles[:40]:
            lines.append(f"      - movie: {title}")
        if len(self.movie_titles) > 40:
            lines.append(f"      … {len(self.movie_titles) - 40} more movies")
        lines.append(f"    series: {len(self.series_ids)}")
        for title in self.series_titles[:40]:
            lines.append(f"      - series: {title}")
        if len(self.series_titles) > 40:
            lines.append(f"      … {len(self.series_titles) - 40} more series")
        lines.extend(
            [
                f"    seasons: {len(self.season_ids)}",
                f"    episodes: {len(self.episode_ids)}",
                f"    media_assets: {len(self.media_asset_ids)}",
                f"    packages: {len(self.package_ids)}",
                f"    artwork_files: {len(self.artwork_files)}",
                f"    media_files: {len(self.media_files)}",
                f"    watch_progress: {len(self.watch_progress_ids)}",
                "  DETACH:",
                f"    media_asset.created_by_admin_id nulls: {len(self.detached_media_asset_admin_refs)}",
                f"    media_package.created_by_admin_id nulls: {len(self.detached_package_admin_refs)}",
                "  RETAIN:",
                f"    admins: {len(self.retained_admin_usernames)} {self.retained_admin_usernames}",
                f"    admin_roles: {len(self.retained_admin_role_names)} {self.retained_admin_role_names}",
                f"    nondemo_movies: {len(self.retained_nondemo_movie_ids)}",
                f"    nondemo_series: {len(self.retained_nondemo_series_ids)}",
                f"    tmdb_demo_movies: {len(self.retained_tmdb_movie_ids)}",
                f"    tmdb_demo_series: {len(self.retained_tmdb_series_ids)}",
                "  TOMBSTONE (audit retained):",
                f"    publication_events: {len(self.publication_event_ids)}",
                "  FK NOTES:",
            ]
        )
        if self.fk_dependent_notes:
            for note in self.fk_dependent_notes:
                lines.append(f"    - {note}")
        else:
            lines.append("    - none")
        return lines


def _is_tmdb_demo_movie(movie: Movie) -> bool:
    return (
        bool(movie.demo_owned)
        and movie.tmdb_id is not None
        and (movie.metadata_source or "").lower() == "tmdb"
    )


def _is_tmdb_demo_series(series: Series) -> bool:
    return (
        bool(series.demo_owned)
        and series.tmdb_id is not None
        and (series.metadata_source or "").lower() == "tmdb"
    )


def _is_fake_demo_movie(movie: Movie) -> bool:
    return bool(movie.demo_owned) and not _is_tmdb_demo_movie(movie)


def _is_fake_demo_series(series: Series) -> bool:
    return bool(series.demo_owned) and not _is_tmdb_demo_series(series)


def build_cleanup_plan(
    db: Session,
    settings: Settings,
    *,
    fake_only: bool = False,
) -> CleanupPlan:
    ownership = load_ownership(settings)
    plan = CleanupPlan(
        fake_only=fake_only,
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

    # Discover demo-owned catalog. Never treat demo-* slugs alone as deletable.
    discovered_movies = [m.id for m in db.query(Movie).filter(Movie.demo_owned.is_(True)).all()]
    plan.movie_ids = sorted(set(plan.movie_ids + discovered_movies))
    discovered_series = [s.id for s in db.query(Series).filter(Series.demo_owned.is_(True)).all()]
    plan.series_ids = sorted(set(plan.series_ids + discovered_series))
    discovered_episodes = [e.id for e in db.query(Episode).filter(Episode.demo_owned.is_(True)).all()]
    plan.episode_ids = sorted(set(plan.episode_ids + discovered_episodes))

    _restrict_plan_to_demo_owned(db, plan)

    if fake_only:
        _restrict_plan_to_fake_demo(db, plan)

    # Expand media assets/packages from remaining catalog targets (ownership may be stale).
    _expand_media_from_catalog(db, plan)

    plan.artwork_files = sorted(set(_discover_demo_artwork_files(db, plan)))

    # Demo subscribers only.
    safe_subs: list[str] = []
    for username in plan.subscriber_usernames:
        subscriber = db.query(Subscriber).filter(Subscriber.username == username).one_or_none()
        if subscriber is None:
            continue
        if subscriber.identity_provider == PROVIDER_DEMO or username.startswith("demo_"):
            safe_subs.append(username)
    plan.subscriber_usernames = safe_subs

    # Admins are always retained — never deleted to satisfy cleanup FKs.
    fixture_names = {f["username"] for f in ADMIN_FIXTURES}
    fixture_roles = {f["role_name"] for f in ADMIN_FIXTURES}
    owned_admins = list(ownership.admin_usernames) or list(fixture_names)
    retained_admins: list[str] = []
    for username in sorted(set(owned_admins) | fixture_names):
        admin = db.query(AdminUser).filter(AdminUser.username == username).one_or_none()
        if admin is not None:
            retained_admins.append(username)
    for admin in db.query(AdminUser).order_by(AdminUser.id).all():
        if admin.username not in retained_admins:
            retained_admins.append(admin.username)
    plan.retained_admin_usernames = retained_admins
    owned_roles = list(ownership.admin_role_names) or list(fixture_roles)
    plan.retained_admin_role_names = sorted(
        {
            role.name
            for role in db.query(AdminRole)
            .filter(AdminRole.name.in_(owned_roles + list(fixture_roles)))
            .all()
        }
        | {r.name for r in db.query(AdminRole).all()}
    )

    plan.retained_nondemo_movie_ids = sorted(
        row[0] for row in db.query(Movie.id).filter(Movie.demo_owned.is_(False)).all()
    )
    plan.retained_nondemo_series_ids = sorted(
        row[0] for row in db.query(Series.id).filter(Series.demo_owned.is_(False)).all()
    )
    plan.retained_tmdb_movie_ids = sorted(
        m.id for m in db.query(Movie).filter(Movie.demo_owned.is_(True)).all() if _is_tmdb_demo_movie(m)
    )
    plan.retained_tmdb_series_ids = sorted(
        s.id for s in db.query(Series).filter(Series.demo_owned.is_(True)).all() if _is_tmdb_demo_series(s)
    )

    plan.fk_dependent_notes = [
        f"{ADMIN_MEDIA_FK_CONSTRAINT}: admin deletion skipped; admins retained",
        "media_packages_created_by_admin_id_fkey: admin deletion skipped; admins retained",
        "media_publication_events have no FK to catalog; events are tombstoned not deleted",
    ]

    if plan.movie_ids:
        movies = db.query(Movie).filter(Movie.id.in_(plan.movie_ids)).order_by(Movie.id).all()
        plan.movie_titles = [
            f"{m.title} (id={m.id}, tmdb={m.tmdb_id}, demo_owned={bool(m.demo_owned)}, "
            f"source={m.metadata_source or ''}, slug={m.slug})"
            for m in movies
        ]
        if any(not bool(m.demo_owned) for m in movies):
            raise RuntimeError("Cleanup plan refused: non-demo movie listed for deletion")
        if fake_only and any(_is_tmdb_demo_movie(m) for m in movies):
            raise RuntimeError("Cleanup plan refused: TMDB demo movie listed in fake-only mode")
    if plan.series_ids:
        series_rows = db.query(Series).filter(Series.id.in_(plan.series_ids)).order_by(Series.id).all()
        plan.series_titles = [
            f"{s.title} (id={s.id}, tmdb={s.tmdb_id}, demo_owned={bool(s.demo_owned)}, "
            f"source={s.metadata_source or ''}, slug={s.slug})"
            for s in series_rows
        ]
        if any(not bool(s.demo_owned) for s in series_rows):
            raise RuntimeError("Cleanup plan refused: non-demo series listed for deletion")
        if fake_only and any(_is_tmdb_demo_series(s) for s in series_rows):
            raise RuntimeError("Cleanup plan refused: TMDB demo series listed in fake-only mode")

    pub_ids: list[int] = []
    for entity_type, ids in (
        ("movie", plan.movie_ids),
        ("series", plan.series_ids),
        ("season", plan.season_ids),
        ("episode", plan.episode_ids),
    ):
        if not ids:
            continue
        pub_ids.extend(
            e.id
            for e in db.query(MediaPublicationEvent)
            .filter(
                MediaPublicationEvent.entity_type == entity_type,
                MediaPublicationEvent.entity_id.in_(ids),
            )
            .all()
        )
    plan.publication_event_ids = sorted(set(pub_ids))
    return plan


def _restrict_plan_to_demo_owned(db: Session, plan: CleanupPlan) -> None:
    """Drop any catalog/media targets that are not demo-owned."""
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


def _restrict_plan_to_fake_demo(db: Session, plan: CleanupPlan) -> None:
    """Keep only synthetic/fake demo rows; retain TMDB-backed demo catalog."""
    fake_movie_ids = {
        m.id
        for m in db.query(Movie).filter(Movie.id.in_(plan.movie_ids or [0])).all()
        if _is_fake_demo_movie(m)
    }
    fake_series_ids = {
        s.id
        for s in db.query(Series).filter(Series.id.in_(plan.series_ids or [0])).all()
        if _is_fake_demo_series(s)
    }
    plan.movie_ids = sorted(fake_movie_ids)
    plan.series_ids = sorted(fake_series_ids)
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
            e.id
            for e in db.query(Episode)
            .filter(Episode.id.in_(plan.episode_ids or [0]), Episode.demo_owned.is_(True))
            .all()
            if e.tmdb_id is None
        )

    deletable_movies = set(plan.movie_ids)
    deletable_episodes = set(plan.episode_ids)
    deletable_series = set(plan.series_ids)
    kept_assets: list[str] = []
    if plan.media_asset_ids:
        for asset in db.query(MediaAsset).filter(MediaAsset.id.in_(plan.media_asset_ids)).all():
            if asset.movie_id is not None and asset.movie_id not in deletable_movies:
                continue
            if asset.episode_id is not None and asset.episode_id not in deletable_episodes:
                continue
            if asset.series_id is not None and asset.series_id not in deletable_series:
                if asset.movie_id is None and asset.episode_id is None:
                    continue
            kept_assets.append(asset.id)
    plan.media_asset_ids = sorted(set(kept_assets))
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


def _expand_media_from_catalog(db: Session, plan: CleanupPlan) -> None:
    """Include media assets/packages attached to catalog rows marked for deletion."""
    asset_ids = set(plan.media_asset_ids)
    if plan.movie_ids:
        asset_ids.update(
            row[0]
            for row in db.query(MediaAsset.id).filter(MediaAsset.movie_id.in_(plan.movie_ids)).all()
        )
    if plan.episode_ids:
        asset_ids.update(
            row[0]
            for row in db.query(MediaAsset.id).filter(MediaAsset.episode_id.in_(plan.episode_ids)).all()
        )
    if plan.series_ids:
        asset_ids.update(
            row[0]
            for row in db.query(MediaAsset.id).filter(MediaAsset.series_id.in_(plan.series_ids)).all()
        )
    plan.media_asset_ids = sorted(asset_ids)
    if plan.media_asset_ids:
        plan.package_ids = sorted(
            set(plan.package_ids)
            | {
                row[0]
                for row in db.query(MediaPackage.id)
                .filter(MediaPackage.media_asset_id.in_(plan.media_asset_ids))
                .all()
            }
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


def _tombstone_publication_events(db: Session, plan: CleanupPlan) -> None:
    """Retain audit rows; sanitize metadata so history survives entity deletion."""
    if not plan.publication_event_ids:
        return
    title_by_key: dict[tuple[str, int], str] = {}
    for movie in db.query(Movie).filter(Movie.id.in_(plan.movie_ids or [0])).all():
        title_by_key[("movie", movie.id)] = movie.title
    for series in db.query(Series).filter(Series.id.in_(plan.series_ids or [0])).all():
        title_by_key[("series", series.id)] = series.title
    for season in db.query(Season).filter(Season.id.in_(plan.season_ids or [0])).all():
        title_by_key[("season", season.id)] = season.title or f"season-{season.season_number}"
    for episode in db.query(Episode).filter(Episode.id.in_(plan.episode_ids or [0])).all():
        title_by_key[("episode", episode.id)] = episode.title

    for event in (
        db.query(MediaPublicationEvent)
        .filter(MediaPublicationEvent.id.in_(plan.publication_event_ids))
        .all()
    ):
        meta = dict(event.metadata_json or {})
        meta["tombstone"] = True
        meta["tombstoned_by"] = "remove_fake_demo" if plan.fake_only else "remove_demo"
        meta["former_entity_type"] = event.entity_type
        meta["former_entity_id"] = event.entity_id
        meta["former_title"] = title_by_key.get((event.entity_type, event.entity_id), "")
        event.metadata_json = meta
        suffix = "demo cleanup tombstone (entity removed; audit retained)"
        event.reason = (event.reason or "") + ("" if not event.reason else " | ") + suffix
        db.add(event)


def _rewrite_ownership_after_partial_cleanup(
    db: Session, settings: Settings, plan: CleanupPlan
) -> None:
    """Keep ownership/markers when TMDB demo catalog remains after fake-only cleanup."""
    remaining_movies = list(db.query(Movie).filter(Movie.demo_owned.is_(True)).all())
    remaining_series = list(db.query(Series).filter(Series.demo_owned.is_(True)).all())
    if not remaining_movies and not remaining_series:
        clear_demo_markers(db)
        clear_ownership_file(settings)
        return

    ownership = load_ownership(settings)
    season_ids = [
        row[0]
        for row in db.query(Season.id)
        .filter(Season.series_id.in_([s.id for s in remaining_series] or [-1]))
        .all()
    ]
    episode_ids = [
        row[0]
        for row in db.query(Episode.id)
        .filter(Episode.series_id.in_([s.id for s in remaining_series] or [-1]))
        .all()
    ]
    asset_ids = [
        row[0]
        for row in db.query(MediaAsset.id)
        .filter(
            (MediaAsset.movie_id.in_([m.id for m in remaining_movies] or [-1]))
            | (MediaAsset.series_id.in_([s.id for s in remaining_series] or [-1]))
            | (MediaAsset.episode_id.in_(episode_ids or [-1]))
        )
        .all()
    ]
    package_ids = [
        row[0]
        for row in db.query(MediaPackage.id)
        .filter(MediaPackage.media_asset_id.in_(asset_ids or ["__none__"]))
        .all()
    ]
    updated = DemoOwnership(
        seed_version=ownership.seed_version or get_setting(db, "DEMO_SEED_VERSION") or "",
        commit_sha=ownership.commit_sha,
        installed_at=ownership.installed_at,
        admin_usernames=list(plan.retained_admin_usernames),
        admin_role_names=list(plan.retained_admin_role_names),
        subscriber_usernames=[
            u for u in ownership.subscriber_usernames if u not in set(plan.subscriber_usernames)
        ],
        genre_ids_created=list(ownership.genre_ids_created),
        genre_slugs=list(ownership.genre_slugs),
        movie_ids=[m.id for m in remaining_movies],
        movie_slugs=[m.slug for m in remaining_movies],
        series_ids=[s.id for s in remaining_series],
        series_slugs=[s.slug for s in remaining_series],
        season_ids=season_ids,
        episode_ids=episode_ids,
        media_asset_ids=asset_ids,
        package_ids=package_ids,
        artwork_files=[],
        media_files=[],
        watch_progress_ids=[],
    )
    save_ownership(settings, updated)


def execute_cleanup(db: Session, settings: Settings, plan: CleanupPlan) -> None:
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

    # Audit: tombstone then keep rows (no FK to catalog entities).
    _tombstone_publication_events(db, plan)

    if plan.episode_ids:
        db.query(Episode).filter(Episode.id.in_(plan.episode_ids)).delete(synchronize_session=False)
    if plan.season_ids:
        db.query(Season).filter(Season.id.in_(plan.season_ids)).delete(synchronize_session=False)
    if plan.series_ids:
        db.query(Series).filter(Series.id.in_(plan.series_ids)).delete(synchronize_session=False)
    if plan.movie_ids:
        db.query(Movie).filter(Movie.id.in_(plan.movie_ids)).delete(synchronize_session=False)

    for genre_id in plan.genre_ids:
        genre = db.get(Genre, genre_id)
        if genre is None:
            continue
        in_movies = db.query(Movie).join(Movie.genre_links).filter(Genre.id == genre_id).count()
        in_series = db.query(Series).join(Series.genre_links).filter(Genre.id == genre_id).count()
        if in_movies == 0 and in_series == 0:
            db.delete(genre)

    # Intentionally do NOT delete admin users or roles.

    if plan.fake_only:
        _rewrite_ownership_after_partial_cleanup(db, settings, plan)
    else:
        remaining = db.query(Movie).filter(Movie.demo_owned.is_(True)).count()
        remaining += db.query(Series).filter(Series.demo_owned.is_(True)).count()
        if remaining == 0:
            clear_demo_markers(db)
        else:
            _rewrite_ownership_after_partial_cleanup(db, settings, plan)

    db.commit()

    art_root = Path(settings.artwork_root)
    for rel in plan.artwork_files:
        path = art_root / rel
        if not (path.is_file() and ("demo-" in path.name or "tmdb-" in path.name)):
            continue
        still_used = False
        for movie in db.query(Movie).all():
            for value in (movie.poster_url, movie.backdrop_url, getattr(movie, "logo_url", "")):
                if rel and rel in (value or ""):
                    still_used = True
                    break
            if still_used:
                break
        if still_used:
            continue
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
                    if any(part in resolved.parts for part in ("originals", "temp", "demo-seed")):
                        resolved.unlink(missing_ok=True)
        except OSError:
            pass

    for package_id in plan.package_ids:
        pkg_dir = root / "packages" / package_id
        if pkg_dir.is_dir():
            shutil.rmtree(pkg_dir, ignore_errors=True)

    if not plan.fake_only:
        demo_temp = root / "temp" / "demo-seed"
        if demo_temp.is_dir():
            shutil.rmtree(demo_temp, ignore_errors=True)
        remaining = db.query(Movie).filter(Movie.demo_owned.is_(True)).count()
        remaining += db.query(Series).filter(Series.demo_owned.is_(True)).count()
        if remaining == 0:
            clear_ownership_file(settings)
            cred = art_root / ".demo" / "credentials.txt"
            if cred.is_file():
                cred.unlink(missing_ok=True)
    else:
        if not plan.retained_tmdb_movie_ids and not plan.retained_tmdb_series_ids:
            cred = art_root / ".demo" / "credentials.txt"
            if cred.is_file():
                cred.unlink(missing_ok=True)
