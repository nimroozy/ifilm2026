"""Publication readiness checks for catalog entities."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.content import Episode, Movie, Season, Series
from app.models.media_assets import MediaAsset
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage, MediaRendition
from app.services.storage import media_root
from app.services.streaming.activation import get_active_completed_package
from app.utils.slug import normalize_slug


@dataclass
class ReadinessIssue:
    code: str
    message: str
    field: str | None = None


@dataclass
class ReadinessResult:
    ready: bool
    issues: list[ReadinessIssue] = field(default_factory=list)
    playable: bool = False
    active_package_id: str | None = None
    package_status: str | None = None

    def add(self, code: str, message: str, *, field: str | None = None) -> None:
        self.issues.append(ReadinessIssue(code=code, message=message, field=field))
        self.ready = False


def _require_text(result: ReadinessResult, value: str | None, *, code: str, message: str, field: str) -> None:
    if not (value or "").strip():
        result.add(code, message, field=field)


def _require_http_url(result: ReadinessResult, value: str | None, *, code: str, message: str, field: str) -> None:
    text = (value or "").strip()
    if not text:
        result.add(code, message, field=field)
        return
    if not (text.startswith("http://") or text.startswith("https://")):
        result.add(f"{code}_invalid", f"{message} must be an http(s) URL", field=field)


def _check_slug(result: ReadinessResult, slug: str | None) -> None:
    if not slug:
        result.add("missing_slug", "Slug is required", field="slug")
        return
    try:
        normalized = normalize_slug(slug)
    except ValueError:
        result.add("invalid_slug", "Slug is invalid", field="slug")
        return
    if normalized != slug:
        result.add("invalid_slug", "Slug is not normalized", field="slug")


def _find_linked_assets(db: Session, *, movie_id: int | None = None, episode_id: int | None = None) -> list[MediaAsset]:
    q = db.query(MediaAsset)
    if movie_id is not None:
        q = q.filter(MediaAsset.movie_id == movie_id)
    elif episode_id is not None:
        q = q.filter(MediaAsset.episode_id == episode_id)
    else:
        return []
    return q.order_by(MediaAsset.created_at.desc()).all()


def _package_integrity(db: Session, package: MediaPackage) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []
    if package.status != "completed":
        issues.append(ReadinessIssue("package_not_completed", f"Active package status is {package.status}"))
    if not package.is_active:
        issues.append(ReadinessIssue("package_inactive", "Package is not active"))
    if package.package_type != PACKAGE_TYPE_HLS_VOD:
        issues.append(ReadinessIssue("package_wrong_type", "Active package is not HLS VOD"))
    if getattr(package, "superseded_at", None) is not None:
        issues.append(ReadinessIssue("package_superseded", "Active package is superseded"))
    renditions = (
        db.query(MediaRendition)
        .filter(MediaRendition.package_id == package.id, MediaRendition.status == "completed")
        .all()
    )
    if not renditions:
        issues.append(ReadinessIssue("package_no_renditions", "Active package has no completed renditions"))
    if not package.master_playlist_path:
        issues.append(ReadinessIssue("package_missing_master", "Active package missing master playlist path"))
    else:
        master = media_root() / package.master_playlist_path
        if not master.is_file():
            issues.append(ReadinessIssue("package_master_missing_file", "Master playlist file is missing on disk"))
    return issues


def evaluate_playable_package(
    db: Session, *, movie_id: int | None = None, episode_id: int | None = None
) -> tuple[bool, str | None, str | None, list[ReadinessIssue]]:
    """Return playable flag, package id, package status, and issues for linked content.

    Playable when an uploaded active HLS package exists OR a validated *primary*
    external URL exists (Option A: unprotected direct — admin/demo policy).
    """
    assets = _find_linked_assets(db, movie_id=movie_id, episode_id=episode_id)
    if not assets:
        return False, None, None, [ReadinessIssue("no_media_asset", "No linked media asset")]

    # Prefer packaged HLS.
    for asset in assets:
        if asset.upload_status in {"failed", "cancelled", "deleted"}:
            continue
        if getattr(asset, "source_type", "uploaded") == "external":
            continue
        if getattr(asset, "deleted_at", None) is not None:
            continue
        package = get_active_completed_package(db, asset.id)
        if package is None:
            continue
        integrity = _package_integrity(db, package)
        if integrity:
            return False, package.id, package.status, integrity
        return True, package.id, package.status, []

    # Primary validated external (exactly one active primary per owner).
    for asset in assets:
        if asset.upload_status in {"failed", "cancelled", "deleted"}:
            continue
        if getattr(asset, "source_type", "uploaded") != "external":
            continue
        if not getattr(asset, "external_is_primary", False):
            continue
        if asset.external_url and asset.external_validated_at:
            return True, None, "external", []
        return (
            False,
            None,
            "external",
            [ReadinessIssue("external_not_validated", "External media URL is not validated")],
        )

    # Surface the most useful failure from the newest asset.
    asset = assets[0]
    if getattr(asset, "source_type", "uploaded") == "external":
        return (
            False,
            None,
            "external",
            [
                ReadinessIssue(
                    "external_not_primary",
                    "No primary validated external media source",
                )
            ],
        )
    if asset.upload_status in {"failed", "cancelled", "deleted"}:
        return (
            False,
            None,
            None,
            [ReadinessIssue("media_asset_unusable", f"Media asset upload status is {asset.upload_status}")],
        )
    package = (
        db.query(MediaPackage)
        .filter(
            MediaPackage.media_asset_id == asset.id,
            MediaPackage.package_type == PACKAGE_TYPE_HLS_VOD,
        )
        .order_by(MediaPackage.created_at.desc())
        .first()
    )
    if package is None:
        return False, None, None, [ReadinessIssue("no_active_hls_package", "No active completed HLS package")]
    if not package.is_active or package.status != "completed":
        return (
            False,
            package.id,
            package.status,
            [ReadinessIssue("no_active_hls_package", "No active completed HLS package")],
        )
    integrity = _package_integrity(db, package)
    return False, package.id, package.status, integrity or [
        ReadinessIssue("no_active_hls_package", "No active completed HLS package")
    ]


def assess_movie_readiness(db: Session, movie: Movie, *, for_publish: bool = True) -> ReadinessResult:
    result = ReadinessResult(ready=True)
    if movie.deleted_at is not None or movie.status == "archived":
        result.add("archived", "Catalog record is archived or deleted")
        return result
    _require_text(result, movie.title, code="missing_title", message="Title is required", field="title")
    _check_slug(result, movie.slug)
    _require_text(result, movie.description or movie.short_description, code="missing_synopsis", message="Synopsis is required", field="description")
    _require_http_url(result, movie.poster_url, code="missing_poster", message="Poster", field="poster_url")
    _require_http_url(result, movie.backdrop_url, code="missing_backdrop", message="Backdrop", field="backdrop_url")
    if movie.release_year is None:
        result.add("missing_year", "Release year is required", field="release_year")
    if not movie.genre_links:
        result.add("missing_genres", "At least one genre is required", field="genre_ids")

    playable, package_id, package_status, issues = evaluate_playable_package(db, movie_id=movie.id)
    result.playable = playable
    result.active_package_id = package_id
    result.package_status = package_status
    if for_publish:
        for issue in issues:
            result.issues.append(issue)
            result.ready = False
        # Option A: unprotected external alone cannot publish production (non-demo) titles.
        if package_status == "external" and playable and not getattr(movie, "demo_owned", False):
            result.add(
                "external_unprotected_production",
                "External media is admin/demo-only (unprotected direct URL). "
                "Upload and activate a packaged HLS source before publishing production content.",
                field="media",
            )
    elif not playable:
        # Still report playability for admin UI without blocking non-publish transitions.
        result.playable = False
    return result


def assess_episode_readiness(db: Session, episode: Episode, *, for_publish: bool = True) -> ReadinessResult:
    result = ReadinessResult(ready=True)
    if episode.deleted_at is not None or episode.status == "archived":
        result.add("archived", "Episode is archived or deleted")
        return result
    season = db.get(Season, episode.season_id)
    series = db.get(Series, episode.series_id)
    if season is None or season.deleted_at is not None:
        result.add("missing_season", "Parent season is missing or deleted")
    if series is None or series.deleted_at is not None:
        result.add("missing_series", "Parent series is missing or deleted")
    if season is not None and season.status == "archived":
        result.add("season_archived", "Parent season is archived")
    if series is not None and series.status == "archived":
        result.add("series_archived", "Parent series is archived")
    _require_text(result, episode.title, code="missing_title", message="Title is required", field="title")
    if episode.episode_number is None or episode.episode_number < 1:
        result.add("invalid_episode_number", "Episode number must be >= 1", field="episode_number")

    playable, package_id, package_status, issues = evaluate_playable_package(db, episode_id=episode.id)
    result.playable = playable
    result.active_package_id = package_id
    result.package_status = package_status
    if for_publish:
        for issue in issues:
            result.issues.append(issue)
            result.ready = False
        demo = bool(getattr(episode, "demo_owned", False))
        if not demo and series is not None:
            demo = bool(getattr(series, "demo_owned", False))
        if package_status == "external" and playable and not demo:
            result.add(
                "external_unprotected_production",
                "External media is admin/demo-only (unprotected direct URL). "
                "Upload and activate a packaged HLS source before publishing production content.",
                field="media",
            )
    return result


def assess_series_readiness(db: Session, series: Series, *, for_publish: bool = True) -> ReadinessResult:
    result = ReadinessResult(ready=True)
    if series.deleted_at is not None or series.status == "archived":
        result.add("archived", "Series is archived or deleted")
        return result
    _require_text(result, series.title, code="missing_title", message="Title is required", field="title")
    _check_slug(result, series.slug)
    _require_text(result, series.description or series.short_description, code="missing_synopsis", message="Synopsis is required", field="description")
    _require_http_url(result, series.poster_url, code="missing_poster", message="Poster", field="poster_url")
    _require_http_url(result, series.backdrop_url, code="missing_backdrop", message="Backdrop", field="backdrop_url")
    if series.release_year is None:
        result.add("missing_year", "Release year is required", field="release_year")
    if not series.genre_links:
        result.add("missing_genres", "At least one genre is required", field="genre_ids")

    if for_publish:
        published_episodes = (
            db.query(Episode)
            .filter(
                Episode.series_id == series.id,
                Episode.deleted_at.is_(None),
                Episode.status == "published",
            )
            .count()
        )
        if published_episodes < 1:
            result.add(
                "no_published_episode",
                "Series requires at least one published episode",
                field="episodes",
            )
    return result


def assess_season_readiness(db: Session, season: Season, *, for_publish: bool = True) -> ReadinessResult:
    result = ReadinessResult(ready=True)
    if season.deleted_at is not None or season.status == "archived":
        result.add("archived", "Season is archived or deleted")
        return result
    series = db.get(Series, season.series_id)
    if series is None or series.deleted_at is not None:
        result.add("missing_series", "Parent series is missing or deleted")
    elif series.status == "archived":
        result.add("series_archived", "Parent series is archived")
    if season.season_number is None or season.season_number < 1:
        result.add("invalid_season_number", "Season number must be >= 1", field="season_number")
    # Seasons are structural; artwork optional. Title defaults to empty.
    return result


def assess_readiness(db: Session, entity_type: str, entity, *, for_publish: bool = True) -> ReadinessResult:
    if entity_type == "movie":
        return assess_movie_readiness(db, entity, for_publish=for_publish)
    if entity_type == "series":
        return assess_series_readiness(db, entity, for_publish=for_publish)
    if entity_type == "season":
        return assess_season_readiness(db, entity, for_publish=for_publish)
    if entity_type == "episode":
        return assess_episode_readiness(db, entity, for_publish=for_publish)
    result = ReadinessResult(ready=False)
    result.add("unknown_entity", f"Unknown entity type {entity_type}")
    return result
