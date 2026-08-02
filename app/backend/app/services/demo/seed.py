"""Idempotent demo catalog seed (safe for staging/demo validation)."""

from __future__ import annotations

import logging
import os
import secrets
import string
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.bootstrap import seed_encoding_profiles
from app.core.config import Settings
from app.core.security import hash_password, verify_password
from app.models.admin import AdminRole, AdminUser
from app.models.content import Episode, Genre, Movie, Season, Series
from app.models.media_encoding import MediaRendition
from app.models.user import Subscriber
from app.models.watch_progress import UserWatchProgress
from app.schemas.watch_history import WatchProgressUpdate
from app.services.demo.artwork import ensure_placeholder_pair
from app.services.demo.constants import (
    ADMIN_FIXTURES,
    DEMO_SEED_VERSION,
    GENRE_NAMES,
    MOVIE_FIXTURES,
    PROVIDER_DEMO,
    SERIES_FIXTURES,
    SUBSCRIBER_FIXTURES,
)
from app.services.demo.media import (
    count_active_demo_packages,
    demo_work_dir,
    upload_and_encode,
)
from app.services.demo.ownership import DemoOwnership, load_ownership, save_ownership, utcnow_iso
from app.services.demo.settings_store import mark_demo_installed
from app.services.publishing import workflow
from app.services.watch_history import upsert_progress
from app.utils.slug import normalize_slug

logger = logging.getLogger(__name__)


@dataclass
class SeedReport:
    seed_version: str = DEMO_SEED_VERSION
    commit_sha: str = ""
    users_added: int = 0
    genres: int = 0
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
            "genres": self.genres,
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


def _generate_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    # Avoid ambiguous characters in operator handoff files.
    alphabet = alphabet.replace("O", "").replace("0", "").replace("l", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _public_base(settings: Settings) -> str:
    """Public origin for artwork absolute URLs.

    Prefer DEMO_PUBLIC_BASE_URL. Otherwise build from PUBLIC_DOMAIN + IFILM_HTTP_PORT
    using http unless HTTPS is explicitly provided. Never default to bare https://host
    when the install only exposes HTTP on :8080.
    """
    explicit = (os.environ.get("DEMO_PUBLIC_BASE_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    domain = (os.environ.get("PUBLIC_DOMAIN") or getattr(settings, "public_domain", "") or "").strip()
    if domain:
        if "://" in domain:
            return domain.rstrip("/")
        port = (os.environ.get("IFILM_HTTP_PORT") or "").strip()
        if port and port not in {"80", "443"}:
            return f"http://{domain}:{port}"
        return f"http://{domain}"
    return "http://127.0.0.1:8080"


def _commit_sha() -> str:
    for key in ("DEMO_SEED_COMMIT_SHA", "APP_COMMIT_SHA", "IFILM_COMMIT_SHA"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def _write_credentials(path: Path, rows: list[tuple[str, str, str]]) -> None:
    """Write credentials with mode 600. Never log password values."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# iFilm demo credentials — root/operator only",
        f"# generated_at={utcnow_iso()}",
        f"# seed_version={DEMO_SEED_VERSION}",
        "# Do not commit. Do not share in tickets or chat.",
        "",
    ]
    for kind, username, password in rows:
        lines.append(f"{kind}\t{username}\t{password}")
    lines.append("")
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def _ensure_role(db: Session, name: str, permissions: list[str], ownership: DemoOwnership) -> AdminRole:
    role = db.query(AdminRole).filter(AdminRole.name == name).one_or_none()
    if role is None:
        role = AdminRole(name=name, permissions=list(permissions))
        db.add(role)
        db.flush()
        ownership.admin_role_names.append(name)
    else:
        # Only mutate roles we own / created for demo.
        if name in set(ownership.admin_role_names) or name in {f["role_name"] for f in ADMIN_FIXTURES}:
            role.permissions = list(permissions)
            ownership.admin_role_names.append(name)
            db.add(role)
    return role


def _seed_admins(
    db: Session, ownership: DemoOwnership, cred_rows: list[tuple[str, str, str]]
) -> int:
    added = 0
    for fixture in ADMIN_FIXTURES:
        role = _ensure_role(db, fixture["role_name"], fixture["permissions"], ownership)
        user = db.query(AdminUser).filter(AdminUser.username == fixture["username"]).one_or_none()
        if user is None:
            password = _generate_password()
            user = AdminUser(
                username=fixture["username"],
                email=fixture["email"],
                full_name=fixture["full_name"],
                hashed_password=hash_password(password),
                role_id=role.id,
                is_active=True,
            )
            db.add(user)
            db.flush()
            cred_rows.append(("admin", fixture["username"], password))
            ownership.admin_usernames.append(fixture["username"])
            added += 1
        else:
            # Existing user: do not overwrite password or role if not demo-owned.
            if fixture["username"] in set(ownership.admin_usernames):
                user.role_id = role.id
                user.is_active = True
                user.email = fixture["email"]
                db.add(user)
            elif user.username == fixture["username"]:
                # Username already present from a prior run without ownership file —
                # adopt only when email matches demo pattern.
                if (user.email or "").endswith("@ifilm.demo"):
                    ownership.admin_usernames.append(fixture["username"])
                    user.role_id = role.id
                    db.add(user)
                else:
                    logger.warning(
                        "Admin username %s already exists; leaving untouched",
                        fixture["username"],
                    )
    return added


def _seed_subscribers(
    db: Session,
    settings: Settings,
    ownership: DemoOwnership,
    cred_rows: list[tuple[str, str, str]],
) -> int:
    added = 0
    now = datetime.now(UTC)
    for fixture in SUBSCRIBER_FIXTURES:
        user = db.query(Subscriber).filter(Subscriber.username == fixture["username"]).one_or_none()
        valid_until = now + timedelta(days=int(fixture["valid_days"]))
        if fixture["expired"]:
            valid_until = now + timedelta(days=int(fixture["valid_days"]))
        expiration = valid_until.date().isoformat()
        if user is None:
            password = _generate_password()
            user = Subscriber(
                username=fixture["username"],
                hashed_password=hash_password(password),
                name=fixture["name"],
                branch=fixture["branch"],
                status=fixture["status"],
                package=fixture["package"],
                expiration=expiration,
                radius_synced=False,
                identity_provider=PROVIDER_DEMO,
                external_subject=fixture["username"],
                max_devices=int(fixture["max_devices"]),
                service_status=fixture["service_status"],
                valid_from=now - timedelta(days=7),
                valid_until=valid_until,
            )
            db.add(user)
            db.flush()
            cred_rows.append(("subscriber", fixture["username"], password))
            ownership.subscriber_usernames.append(fixture["username"])
            added += 1
        else:
            owned = fixture["username"] in set(ownership.subscriber_usernames)
            demo_like = user.identity_provider == PROVIDER_DEMO or (
                user.username.startswith("demo_") and not user.radius_synced
            )
            if owned or demo_like:
                ownership.subscriber_usernames.append(fixture["username"])
                user.name = fixture["name"]
                user.branch = fixture["branch"]
                user.status = fixture["status"]
                user.package = fixture["package"]
                user.expiration = expiration
                user.identity_provider = PROVIDER_DEMO
                user.external_subject = fixture["username"]
                user.max_devices = int(fixture["max_devices"])
                user.service_status = fixture["service_status"]
                user.valid_from = now - timedelta(days=7)
                user.valid_until = valid_until
                user.radius_synced = False
                if not user.hashed_password:
                    password = _generate_password()
                    user.hashed_password = hash_password(password)
                    cred_rows.append(("subscriber", fixture["username"], password))
                db.add(user)
            else:
                logger.warning(
                    "Subscriber %s exists and is not demo-owned; leaving untouched",
                    fixture["username"],
                )
    return added


def _ensure_genres(db: Session, ownership: DemoOwnership) -> dict[str, Genre]:
    by_name: dict[str, Genre] = {}
    for name in GENRE_NAMES:
        slug = normalize_slug(name)
        genre = db.query(Genre).filter(Genre.slug == slug).one_or_none()
        if genre is None:
            genre = Genre(name=name, slug=slug, description=f"Demo genre: {name}")
            db.add(genre)
            db.flush()
            ownership.genre_ids_created.append(genre.id)
        ownership.genre_slugs.append(slug)
        by_name[name] = genre
    return by_name


def _apply_status_path(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    path: str,
    actor: AdminUser,
    scheduled_at: datetime | None = None,
) -> None:
    """Drive workflow transitions. Uses skip_readiness only for non-playable examples."""
    entity = workflow.get_entity(db, entity_type, entity_id)
    current = entity.status
    if current == path:
        return

    def go(to_status: str, *, skip_readiness: bool = False, scheduled_publish_at=None) -> None:
        workflow.transition(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            to_status=to_status,
            actor=actor,
            reason="demo seed",
            skip_readiness=skip_readiness,
            scheduled_publish_at=scheduled_publish_at,
        )

    # Normalize back to a known state when re-seeding owned rows.
    if current not in {"draft", path}:
        if current == "published" and path != "published":
            if path == "unpublished":
                go("unpublished", skip_readiness=True)
                return
            if path == "archived":
                go("archived", skip_readiness=True)
                return
        # Best-effort reset via archive is irreversible for workflow; leave as-is if mismatch.
        if current != path:
            logger.info(
                "Demo %s %s already in status=%s; target=%s (leaving)",
                entity_type,
                entity_id,
                current,
                path,
            )
            return

    if path == "draft":
        return
    if path == "in_review":
        go("in_review", skip_readiness=True)
        return
    if path == "approved":
        go("in_review", skip_readiness=True)
        go("approved", skip_readiness=True)
        return
    if path == "scheduled":
        go("in_review", skip_readiness=True)
        go("approved", skip_readiness=True)
        when = scheduled_at or (datetime.now(UTC) + timedelta(days=7))
        go("scheduled", skip_readiness=True, scheduled_publish_at=when)
        return
    if path == "published":
        go("in_review", skip_readiness=False)
        go("approved", skip_readiness=False)
        go("published", skip_readiness=False)
        return
    if path == "unpublished":
        # Publish first (skip readiness for examples without media), then unpublish.
        go("in_review", skip_readiness=True)
        go("approved", skip_readiness=True)
        go("published", skip_readiness=True)
        go("unpublished", skip_readiness=True)
        return
    if path == "archived":
        go("archived", skip_readiness=True)
        return


def _seed_movies(
    db: Session,
    settings: Settings,
    ownership: DemoOwnership,
    genres: dict[str, Genre],
    actor: AdminUser,
    report: SeedReport,
    *,
    skip_media: bool = False,
) -> dict[str, Movie]:
    base = _public_base(settings)
    by_slug: dict[str, Movie] = {}
    for fixture in MOVIE_FIXTURES:
        slug = fixture["slug"]
        movie = db.query(Movie).filter(Movie.slug == slug).one_or_none()
        poster_url, backdrop_url, art_files = ensure_placeholder_pair(
            settings,
            slug=slug,
            title=fixture["title"],
            color=fixture["color"],
            public_base_url=base,
        )
        ownership.artwork_files.extend(art_files)
        genre_links = [genres[n] for n in fixture["genres"] if n in genres]
        if movie is None:
            movie = Movie(
                title=fixture["title"],
                original_title=fixture["original_title"],
                slug=slug,
                description=fixture["description"],
                short_description=fixture["short_description"],
                release_year=fixture["release_year"],
                country=fixture["country"],
                duration_minutes=fixture["duration_minutes"],
                language=fixture["language"],
                age_rating="PG-13",
                poster_url=poster_url,
                backdrop_url=backdrop_url,
                status="draft",
                is_featured=bool(fixture["is_featured"]),
                is_trending=bool(fixture["is_trending"]),
                genre_links=genre_links,
            )
            db.add(movie)
            db.flush()
        else:
            if slug not in set(ownership.movie_slugs) and movie.id not in set(ownership.movie_ids):
                # Adopt only demo-prefixed slugs.
                if not slug.startswith("demo-"):
                    report.deviations.append(f"Skipped non-owned movie slug collision: {slug}")
                    continue
            movie.title = fixture["title"]
            movie.original_title = fixture["original_title"]
            movie.description = fixture["description"]
            movie.short_description = fixture["short_description"]
            movie.release_year = fixture["release_year"]
            movie.country = fixture["country"]
            movie.duration_minutes = fixture["duration_minutes"]
            movie.language = fixture["language"]
            movie.poster_url = poster_url
            movie.backdrop_url = backdrop_url
            movie.is_featured = bool(fixture["is_featured"])
            movie.is_trending = bool(fixture["is_trending"])
            movie.genre_links = genre_links
            db.add(movie)
            db.flush()
        ownership.movie_ids.append(movie.id)
        ownership.movie_slugs.append(slug)
        by_slug[slug] = movie

        with_media = bool(fixture.get("with_media")) and not skip_media
        if with_media:
            try:
                upload_and_encode(
                    db,
                    settings=settings,
                    admin=actor,
                    ownership=ownership,
                    work_dir=demo_work_dir(settings),
                    label=slug,
                    movie_id=movie.id,
                    duration_seconds=20,
                )
            except Exception as exc:  # noqa: BLE001 — continue seeding other titles
                db.rollback()
                report.deviations.append(f"Media pipeline failed for {slug}: {exc}")
                logger.exception("Demo media failed for %s", slug)

        target = fixture["status_path"]
        try:
            if target == "published":
                before = movie.status
                _publish_entity(db, "movie", movie.id, actor, report, slug)
                db.refresh(movie)
                if movie.status != "published" and before != "published":
                    report.deviations.append(f"{slug}: failed to reach published")
            else:
                _apply_status_path(
                    db,
                    entity_type="movie",
                    entity_id=movie.id,
                    path=target,
                    actor=actor,
                )
        except Exception as exc:  # noqa: BLE001
            report.deviations.append(f"Publish path failed for {slug}: {exc}")
            logger.exception("Publish path failed for %s", slug)

    return by_slug


def _seed_series(
    db: Session,
    settings: Settings,
    ownership: DemoOwnership,
    genres: dict[str, Genre],
    actor: AdminUser,
    report: SeedReport,
    *,
    skip_media: bool = False,
) -> None:
    base = _public_base(settings)
    for fixture in SERIES_FIXTURES:
        slug = fixture["slug"]
        series = db.query(Series).filter(Series.slug == slug).one_or_none()
        poster_url, backdrop_url, art_files = ensure_placeholder_pair(
            settings,
            slug=slug,
            title=fixture["title"],
            color=fixture["color"],
            public_base_url=base,
        )
        ownership.artwork_files.extend(art_files)
        genre_links = [genres[n] for n in fixture["genres"] if n in genres]
        if series is None:
            series = Series(
                title=fixture["title"],
                original_title=fixture["original_title"],
                slug=slug,
                description=fixture["description"],
                short_description=fixture["short_description"],
                release_year=fixture["release_year"],
                country=fixture["country"],
                language=fixture["language"],
                age_rating="PG-13",
                poster_url=poster_url,
                backdrop_url=backdrop_url,
                status="draft",
                is_featured=fixture["mode"] == "fully_published",
                is_trending=fixture["mode"] == "partial",
                genre_links=genre_links,
            )
            db.add(series)
            db.flush()
        else:
            series.title = fixture["title"]
            series.original_title = fixture["original_title"]
            series.description = fixture["description"]
            series.short_description = fixture["short_description"]
            series.poster_url = poster_url
            series.backdrop_url = backdrop_url
            series.genre_links = genre_links
            db.add(series)
            db.flush()
        ownership.series_ids.append(series.id)
        ownership.series_slugs.append(slug)

        episode_media_done = 0
        for season_number in (1, 2):
            season = (
                db.query(Season)
                .filter(Season.series_id == series.id, Season.season_number == season_number)
                .one_or_none()
            )
            if season is None:
                season = Season(
                    series_id=series.id,
                    season_number=season_number,
                    title=f"Season {season_number}",
                    description=f"Demo season {season_number} of {fixture['title']}",
                    status="draft",
                )
                db.add(season)
                db.flush()
            ownership.season_ids.append(season.id)

            for ep_number in (1, 2, 3):
                episode = (
                    db.query(Episode)
                    .filter(Episode.season_id == season.id, Episode.episode_number == ep_number)
                    .one_or_none()
                )
                title = f"{fixture['title']} S{season_number}E{ep_number}"
                if episode is None:
                    episode = Episode(
                        season_id=season.id,
                        series_id=series.id,
                        episode_number=ep_number,
                        title=title,
                        description=f"Demo episode {ep_number} of season {season_number}.",
                        duration_minutes=42 + ep_number,
                        thumbnail_url=poster_url,
                        status="draft",
                    )
                    db.add(episode)
                    db.flush()
                else:
                    episode.title = title
                    episode.description = f"Demo episode {ep_number} of season {season_number}."
                    episode.duration_minutes = 42 + ep_number
                    episode.thumbnail_url = poster_url
                    db.add(episode)
                    db.flush()
                ownership.episode_ids.append(episode.id)

                want_media = (
                    bool(fixture.get("with_episode_media"))
                    and not skip_media
                    and episode_media_done < (2 if fixture["mode"] != "draft" else 0)
                )
                # Prefer S1E1 and S1E2 for media on publishable series.
                if want_media and season_number == 1 and ep_number in {1, 2}:
                    try:
                        upload_and_encode(
                            db,
                            settings=settings,
                            admin=actor,
                            ownership=ownership,
                            work_dir=demo_work_dir(settings),
                            label=f"{slug}-s{season_number}e{ep_number}",
                            # Media assets allow only one owner FK (episode XOR series/season/movie).
                            episode_id=episode.id,
                            duration_seconds=18,
                        )
                        episode_media_done += 1
                    except Exception as exc:  # noqa: BLE001
                        db.rollback()
                        report.deviations.append(
                            f"Episode media failed for {slug} S{season_number}E{ep_number}: {exc}"
                        )

        # Publication modes
        seasons = (
            db.query(Season)
            .filter(Season.series_id == series.id)
            .order_by(Season.season_number)
            .all()
        )
        mode = fixture["mode"]
        try:
            if mode == "draft":
                return_point = None
                _ = return_point
                # leave everything draft
            elif mode == "fully_published":
                for season in seasons:
                    for episode in (
                        db.query(Episode)
                        .filter(Episode.season_id == season.id)
                        .order_by(Episode.episode_number)
                        .all()
                    ):
                        _publish_entity(db, "episode", episode.id, actor, report, slug)
                    _publish_entity(db, "season", season.id, actor, report, slug)
                _publish_entity(db, "series", series.id, actor, report, slug)
            elif mode == "partial":
                # Publish series + season 1 + episodes 1-2; leave rest draft / in_review
                s1 = seasons[0]
                eps = (
                    db.query(Episode)
                    .filter(Episode.season_id == s1.id)
                    .order_by(Episode.episode_number)
                    .all()
                )
                for episode in eps[:2]:
                    _publish_entity(db, "episode", episode.id, actor, report, slug)
                if len(eps) >= 3:
                    _apply_status_path(
                        db,
                        entity_type="episode",
                        entity_id=eps[2].id,
                        path="in_review",
                        actor=actor,
                    )
                _publish_entity(db, "season", s1.id, actor, report, slug)
                _publish_entity(db, "series", series.id, actor, report, slug)
                # Season 2 stays draft
        except Exception as exc:  # noqa: BLE001
            report.deviations.append(f"Series publish mode failed for {slug}: {exc}")


def _publish_entity(
    db: Session,
    entity_type: str,
    entity_id: int,
    actor: AdminUser,
    report: Any,
    label: str,
) -> None:
    entity = workflow.get_entity(db, entity_type, entity_id)
    if entity.status == "published":
        return
    try:
        if entity.status == "draft":
            workflow.transition(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                to_status="in_review",
                actor=actor,
                reason="demo seed",
            )
            entity = workflow.get_entity(db, entity_type, entity_id)
        if entity.status == "in_review":
            workflow.transition(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                to_status="approved",
                actor=actor,
                reason="demo seed",
            )
            entity = workflow.get_entity(db, entity_type, entity_id)
        if entity.status == "approved":
            workflow.transition(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                to_status="published",
                actor=actor,
                reason="demo seed",
            )
    except Exception as exc:  # noqa: BLE001
        # Episodes without packages: skip_readiness for structural publish examples
        try:
            if entity.status == "draft":
                workflow.transition(
                    db,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    to_status="in_review",
                    actor=actor,
                    reason="demo seed fallback",
                    skip_readiness=True,
                )
            entity = workflow.get_entity(db, entity_type, entity_id)
            if entity.status == "in_review":
                workflow.transition(
                    db,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    to_status="approved",
                    actor=actor,
                    reason="demo seed fallback",
                    skip_readiness=True,
                )
            entity = workflow.get_entity(db, entity_type, entity_id)
            if entity.status == "approved":
                workflow.transition(
                    db,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    to_status="published",
                    actor=actor,
                    reason="demo seed fallback",
                    skip_readiness=True,
                )
            report.deviations.append(
                f"{label} {entity_type}:{entity_id} published with skip_readiness ({exc})"
            )
        except Exception as exc2:  # noqa: BLE001
            report.deviations.append(f"{label} {entity_type}:{entity_id} publish failed: {exc2}")


def _seed_watch_history(
    db: Session,
    ownership: DemoOwnership,
    movies: dict[str, Movie],
    report: SeedReport,
) -> None:
    subscriber = (
        db.query(Subscriber).filter(Subscriber.username == "demo_active").one_or_none()
    )
    if subscriber is None:
        report.deviations.append("demo_active missing; skipped watch history")
        return

    def asset_for_movie(slug: str):
        movie = movies.get(slug)
        if movie is None:
            return None, None
        from app.models.media_assets import MediaAsset

        asset = (
            db.query(MediaAsset)
            .filter(MediaAsset.movie_id == movie.id, MediaAsset.upload_status == "completed")
            .order_by(MediaAsset.created_at.desc())
            .first()
        )
        return movie, asset

    # 35% movie
    _, asset = asset_for_movie("demo-kabul-nights")
    if asset and asset.duration_seconds:
        duration = float(asset.duration_seconds)
        existing = (
            db.query(UserWatchProgress)
            .filter(
                UserWatchProgress.subscriber_id == subscriber.id,
                UserWatchProgress.media_asset_id == asset.id,
            )
            .one_or_none()
        )
        if existing is None or existing.id in set(ownership.watch_progress_ids) or True:
            out = upsert_progress(
                db,
                subscriber,
                asset.id,
                WatchProgressUpdate(position_seconds=duration * 0.35, duration_seconds=duration),
            )
            ownership.watch_progress_ids.append(out.id)

    # completed movie
    _, asset = asset_for_movie("demo-the-last-caravan")
    if asset and asset.duration_seconds:
        duration = float(asset.duration_seconds)
        out = upsert_progress(
            db,
            subscriber,
            asset.id,
            WatchProgressUpdate(position_seconds=duration * 0.95, duration_seconds=duration),
            force_complete=True,
        )
        ownership.watch_progress_ids.append(out.id)

    # 60% episode
    from app.models.media_assets import MediaAsset

    ep_asset = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.episode_id.in_(ownership.episode_ids or [0]),
            MediaAsset.upload_status == "completed",
        )
        .order_by(MediaAsset.created_at.asc())
        .first()
    )
    if ep_asset and ep_asset.duration_seconds:
        duration = float(ep_asset.duration_seconds)
        out = upsert_progress(
            db,
            subscriber,
            ep_asset.id,
            WatchProgressUpdate(position_seconds=duration * 0.60, duration_seconds=duration),
        )
        ownership.watch_progress_ids.append(out.id)
    else:
        report.deviations.append("No episode asset for watch history 60% progress")


def _pick_actor(db: Session) -> AdminUser:
    for username in ("publisher", "catalog_manager", "admin"):
        user = db.query(AdminUser).filter(AdminUser.username == username, AdminUser.is_active.is_(True)).one_or_none()
        if user is not None:
            return user
    user = db.query(AdminUser).filter(AdminUser.is_active.is_(True)).order_by(AdminUser.id.asc()).first()
    if user is None:
        raise RuntimeError("No admin user available to act as publishing actor")
    return user


def run_seed(
    db: Session,
    settings: Settings,
    *,
    credentials_path: Path | None = None,
    skip_media: bool = False,
) -> SeedReport:
    report = SeedReport(seed_version=DEMO_SEED_VERSION, commit_sha=_commit_sha())
    ownership = load_ownership(settings)
    if not ownership.installed_at:
        ownership.installed_at = utcnow_iso()
    ownership.seed_version = DEMO_SEED_VERSION
    ownership.commit_sha = report.commit_sha

    seed_encoding_profiles(db)
    cred_rows: list[tuple[str, str, str]] = []

    report.users_added += _seed_admins(db, ownership, cred_rows)
    report.users_added += _seed_subscribers(db, settings, ownership, cred_rows)
    db.flush()

    genres = _ensure_genres(db, ownership)
    report.genres = len(GENRE_NAMES)

    actor = _pick_actor(db)

    if skip_media:
        report.deviations.append("skip_media=1: no synthetic video / HLS generation")

    movies = _seed_movies(
        db, settings, ownership, genres, actor, report, skip_media=skip_media
    )
    _seed_series(
        db, settings, ownership, genres, actor, report, skip_media=skip_media
    )
    db.flush()
    _seed_watch_history(db, ownership, movies, report)

    mark_demo_installed(
        db,
        version=DEMO_SEED_VERSION,
        commit_sha=report.commit_sha,
        installed_at=ownership.installed_at,
    )
    db.commit()
    save_ownership(settings, ownership)

    # Credentials: merge with existing file passwords when re-run added none.
    cred_path = credentials_path or Path(
        os.environ.get("DEMO_CREDENTIALS_PATH")
        or str(Path(settings.artwork_root) / ".demo" / "credentials.txt")
    )
    if cred_rows:
        # Preserve previously written passwords for users not regenerated.
        existing_map: dict[tuple[str, str], str] = {}
        if cred_path.is_file():
            for line in cred_path.read_text(encoding="utf-8").splitlines():
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    existing_map[(parts[0], parts[1])] = parts[2]
        for kind, username, password in cred_rows:
            existing_map[(kind, username)] = password
        merged = [(k[0], k[1], v) for k, v in sorted(existing_map.items())]
        _write_credentials(cred_path, merged)
    report.credentials_path = str(cred_path)

    report.movies = len(ownership.movie_ids)
    report.series = len(ownership.series_ids)
    report.seasons = len(ownership.season_ids)
    report.episodes = len(ownership.episode_ids)
    report.media_assets = len(set(ownership.media_asset_ids))
    report.active_hls_packages = count_active_demo_packages(db, ownership)
    report.published_items = (
        db.query(Movie).filter(Movie.id.in_(ownership.movie_ids or [0]), Movie.status == "published").count()
        + db.query(Series).filter(Series.id.in_(ownership.series_ids or [0]), Series.status == "published").count()
        + db.query(Episode).filter(Episode.id.in_(ownership.episode_ids or [0]), Episode.status == "published").count()
    )

    # Sanity: 240p/360p present on at least one package
    if ownership.package_ids:
        rendition_heights = {
            int(r.height)
            for r in db.query(MediaRendition)
            .filter(
                MediaRendition.package_id.in_(ownership.package_ids),
                MediaRendition.status == "completed",
            )
            .all()
        }
        if ownership.media_asset_ids and (240 not in rendition_heights or 360 not in rendition_heights):
            report.deviations.append(
                f"Expected 240p+360p renditions; observed heights={sorted(rendition_heights)}"
            )

    return report


def password_still_valid(db: Session, username: str, password: str) -> bool:
    user = db.query(Subscriber).filter(Subscriber.username == username).one_or_none()
    if user is None or not user.hashed_password:
        return False
    return verify_password(password, user.hashed_password)
