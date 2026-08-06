"""Import TMDB movie/series metadata into the local catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.content import Episode, Genre, Movie, Season, Series
from app.services.tmdb.artwork import ArtworkError, build_image_url, download_artwork
from app.services.tmdb.client import TMDBClient
from app.services.tmdb.trailers import TrailerMetadata, select_trailer
from app.utils.slug import normalize_slug, slug_or_from_title

MediaType = Literal["movie", "series"]


@dataclass
class ImportResult:
    media_type: MediaType
    entity_id: int
    tmdb_id: int
    created: bool
    artwork_files: list[str] = field(default_factory=list)
    episode_ids: list[int] = field(default_factory=list)
    season_ids: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _year(value: str | None) -> int | None:
    parsed = _parse_date(value)
    return parsed.year if parsed else None


def _language_name(details: dict[str, Any]) -> str:
    original = str(details.get("original_language") or "")
    for lang in details.get("spoken_languages") or []:
        if not isinstance(lang, dict):
            continue
        if lang.get("iso_639_1") == original:
            return str(lang.get("english_name") or lang.get("name") or original)
    return original


def _country(details: dict[str, Any], key: str) -> str:
    countries = details.get(key) or []
    if isinstance(countries, list) and countries:
        first = countries[0]
        if isinstance(first, dict):
            return str(first.get("iso_3166_1") or first.get("name") or "")
        if isinstance(first, str):
            return first
    return ""


def _fallback_text(primary: str, fallback: str) -> str:
    return primary.strip() or fallback.strip()


def _translation(details: dict[str, Any], language: str) -> dict[str, Any]:
    translations = ((details.get("translations") or {}).get("translations") or [])
    wanted = (language or "").split("-", 1)[0].lower()
    for item in translations:
        if not isinstance(item, dict):
            continue
        if str(item.get("iso_639_1") or "").lower() == wanted:
            data = item.get("data")
            if isinstance(data, dict):
                return data
    return {}


def _apply_translation_fallback(details: dict[str, Any], *, media_type: MediaType, settings: Settings) -> dict[str, str]:
    title_key = "title" if media_type == "movie" else "name"
    original_key = "original_title" if media_type == "movie" else "original_name"
    fallback = _translation(details, settings.tmdb_fallback_language)
    title = _fallback_text(str(details.get(title_key) or ""), str(fallback.get(title_key) or ""))
    overview = _fallback_text(str(details.get("overview") or ""), str(fallback.get("overview") or ""))
    return {
        "title": title or str(details.get(original_key) or f"TMDB {details.get('id')}"),
        "original_title": str(details.get(original_key) or title),
        "overview": overview,
    }


def _short_description(text: str) -> str:
    text = " ".join((text or "").split())
    if len(text) <= 500:
        return text
    return text[:497].rstrip() + "..."


def _ensure_unique_slug(db: Session, model: type[Movie] | type[Series], title: str, tmdb_id: int, existing_id: int | None) -> str:
    base = slug_or_from_title(None, title)
    candidate = base
    n = 2
    while True:
        q = db.query(model).filter(model.slug == candidate, model.deleted_at.is_(None))
        if existing_id is not None:
            q = q.filter(model.id != existing_id)
        if q.first() is None:
            return candidate
        candidate = f"{base}-{int(tmdb_id)}" if n == 2 else f"{base}-{int(tmdb_id)}-{n}"
        n += 1


def _ensure_genres(db: Session, details: dict[str, Any]) -> list[Genre]:
    genres: list[Genre] = []
    for item in details.get("genres") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        slug = normalize_slug(name)
        genre = db.query(Genre).filter(Genre.slug == slug).one_or_none()
        if genre is None:
            genre = Genre(name=name, slug=slug, description=f"Imported from TMDB genre: {name}")
            db.add(genre)
            db.flush()
        genres.append(genre)
    return genres


def _dedupe_imdb(db: Session, model: type[Movie] | type[Series], imdb_id: str | None, entity_id: int | None) -> str | None:
    if not imdb_id:
        return None
    q = db.query(model).filter(model.imdb_id == imdb_id)
    if entity_id is not None:
        q = q.filter(model.id != entity_id)
    return None if q.first() is not None else imdb_id


def _choose_logo(details: dict[str, Any]) -> str:
    logos = ((details.get("images") or {}).get("logos") or [])
    if not isinstance(logos, list):
        return ""
    for item in logos:
        if isinstance(item, dict) and item.get("file_path"):
            return str(item["file_path"])
    return ""


def _store_artwork(
    settings: Settings,
    *,
    details: dict[str, Any],
    media_type: MediaType,
    tmdb_configuration: dict[str, Any] | None,
) -> tuple[dict[str, str], list[str], list[str]]:
    tmdb_id = int(details["id"])
    paths = {
        "poster_url": ("poster", details.get("poster_path")),
        "backdrop_url": ("backdrop", details.get("backdrop_path")),
        "logo_url": ("logo", _choose_logo(details)),
    }
    urls: dict[str, str] = {}
    files: list[str] = []
    warnings: list[str] = []
    for field_name, (kind, path) in paths.items():
        if not path:
            if kind == "poster":
                warnings.append(f"required poster missing for TMDB {tmdb_id}")
            continue
        url = build_image_url(settings, str(path), size="original")
        try:
            stored = download_artwork(
                settings,
                url,
                kind=kind,
                tmdb_id=tmdb_id,
                tmdb_configuration=tmdb_configuration,
            )
        except ArtworkError as exc:
            # Optional logo/backdrop failures must not fail the import. A missing
            # required poster is reported clearly via ImportResult.warnings.
            if kind == "poster":
                warnings.append(f"required poster download failed for TMDB {tmdb_id}: {exc}")
            continue
        urls[field_name] = stored.url
        files.append(stored.relative_path)
    return urls, files, warnings


def _store_episode_still(
    settings: Settings,
    *,
    still_path: str,
    tmdb_episode_id: int,
    tmdb_configuration: dict[str, Any] | None,
) -> tuple[str, str] | None:
    """Download an episode still when TMDB provides still_path. Optional — never fails import."""
    if not still_path:
        return None
    url = build_image_url(settings, str(still_path), size="original")
    try:
        stored = download_artwork(
            settings,
            url,
            kind="still",
            tmdb_id=int(tmdb_episode_id),
            tmdb_configuration=tmdb_configuration,
        )
    except ArtworkError:
        return None
    return stored.url, stored.relative_path


def _apply_trailer(entity: Movie | Series, trailer: TrailerMetadata | None) -> None:
    if trailer is None:
        entity.trailer_url = ""
        entity.trailer_provider = ""
        entity.trailer_key = ""
        entity.trailer_title = ""
        entity.trailer_official = False
        entity.trailer_language = ""
        entity.trailer_published_at = None
        return
    entity.trailer_url = trailer.embed_url
    entity.trailer_provider = trailer.provider
    entity.trailer_key = trailer.key
    entity.trailer_title = trailer.title
    entity.trailer_official = trailer.official
    entity.trailer_language = trailer.language
    entity.trailer_published_at = trailer.published_at


def _base_movie_fields(details: dict[str, Any], settings: Settings) -> dict[str, Any]:
    text = _apply_translation_fallback(details, media_type="movie", settings=settings)
    release_date = _parse_date(details.get("release_date"))
    return {
        "title": text["title"],
        "original_title": text["original_title"],
        "description": text["overview"],
        "short_description": _short_description(text["overview"]),
        "release_year": release_date.year if release_date else None,
        "release_date": release_date,
        "duration_minutes": details.get("runtime"),
        "language": _language_name(details),
        "country": _country(details, "production_countries"),
        "imdb_id": ((details.get("external_ids") or {}).get("imdb_id") or details.get("imdb_id") or None),
        "imdb_rating": details.get("vote_average"),
        "spoken_languages": details.get("spoken_languages") or [],
    }


def _base_series_fields(details: dict[str, Any], settings: Settings) -> dict[str, Any]:
    text = _apply_translation_fallback(details, media_type="series", settings=settings)
    first = _parse_date(details.get("first_air_date"))
    last = _parse_date(details.get("last_air_date"))
    return {
        "title": text["title"],
        "original_title": text["original_title"],
        "description": text["overview"],
        "short_description": _short_description(text["overview"]),
        "release_year": first.year if first else None,
        "end_year": last.year if last and (details.get("status") or "").lower() == "ended" else None,
        "language": _language_name(details),
        "country": _country(details, "origin_country"),
        "imdb_id": (details.get("external_ids") or {}).get("imdb_id") or None,
        "imdb_rating": details.get("vote_average"),
        "spoken_languages": details.get("spoken_languages") or [],
        "airing_status": str(details.get("status") or "Ongoing"),
    }


def import_movie(
    db: Session,
    settings: Settings,
    tmdb_id: int,
    *,
    client: TMDBClient | None = None,
    demo_owned: bool = False,
    seed_version: str = "",
    force: bool = False,
    download_images: bool = True,
) -> ImportResult:
    client = client or TMDBClient(settings)
    existing = db.query(Movie).filter(Movie.tmdb_id == int(tmdb_id)).one_or_none()
    if existing is not None and existing.demo_owned is False and not force:
        return ImportResult("movie", existing.id, int(tmdb_id), created=False)
    if existing is not None and existing.demo_owned is False and demo_owned:
        return ImportResult("movie", existing.id, int(tmdb_id), created=False)

    details = client.movie_details(int(tmdb_id))
    if not details.get("overview") and settings.tmdb_fallback_language != settings.tmdb_language:
        details = {**details, **client.movie_details(int(tmdb_id), language=settings.tmdb_fallback_language)}
    videos = client.movie_videos(int(tmdb_id))
    trailer = select_trailer(videos, language=settings.tmdb_language)
    config = client.configuration() if download_images else None

    created = existing is None
    movie = existing or Movie(tmdb_id=int(tmdb_id), status="draft")
    fields = _base_movie_fields(details, settings)
    fields["imdb_id"] = _dedupe_imdb(db, Movie, fields.get("imdb_id"), movie.id if existing is not None else None)
    for key, value in fields.items():
        setattr(movie, key, value)
    movie.tmdb_id = int(tmdb_id)
    movie.metadata_source = "tmdb"
    movie.demo_owned = bool(movie.demo_owned or demo_owned)
    movie.demo_seed_version = seed_version if demo_owned else (movie.demo_seed_version or "")
    movie.imported_at = movie.imported_at or utcnow()
    movie.metadata_updated_at = utcnow()
    if created:
        movie.slug = _ensure_unique_slug(db, Movie, movie.title, int(tmdb_id), None)
        movie.status = "draft"
    movie.genre_links = _ensure_genres(db, details)
    _apply_trailer(movie, trailer)

    artwork_files: list[str] = []
    warnings: list[str] = []
    if download_images:
        urls, artwork_files, warnings = _store_artwork(
            settings, details=details, media_type="movie", tmdb_configuration=config
        )
        for field, url in urls.items():
            setattr(movie, field, url)

    db.add(movie)
    db.flush()
    return ImportResult(
        "movie",
        movie.id,
        int(tmdb_id),
        created=created,
        artwork_files=artwork_files,
        warnings=warnings,
    )


def _season_name(season_number: int, season_details: dict[str, Any]) -> str:
    return str(season_details.get("name") or f"Season {season_number}")


def import_series(
    db: Session,
    settings: Settings,
    tmdb_id: int,
    *,
    client: TMDBClient | None = None,
    demo_owned: bool = False,
    seed_version: str = "",
    force: bool = False,
    seasons_limit: int | None = None,
    episodes_per_season: int | None = None,
    download_images: bool = True,
) -> ImportResult:
    client = client or TMDBClient(settings)
    existing = db.query(Series).filter(Series.tmdb_id == int(tmdb_id)).one_or_none()
    if existing is not None and existing.demo_owned is False and not force:
        return ImportResult("series", existing.id, int(tmdb_id), created=False)
    if existing is not None and existing.demo_owned is False and demo_owned:
        return ImportResult("series", existing.id, int(tmdb_id), created=False)

    details = client.tv_details(int(tmdb_id))
    if not details.get("overview") and settings.tmdb_fallback_language != settings.tmdb_language:
        details = {**details, **client.tv_details(int(tmdb_id), language=settings.tmdb_fallback_language)}
    videos = client.tv_videos(int(tmdb_id))
    trailer = select_trailer(videos, language=settings.tmdb_language)
    config = client.configuration() if download_images else None

    created = existing is None
    series = existing or Series(tmdb_id=int(tmdb_id), status="draft")
    fields = _base_series_fields(details, settings)
    fields["imdb_id"] = _dedupe_imdb(db, Series, fields.get("imdb_id"), series.id if existing is not None else None)
    for key, value in fields.items():
        setattr(series, key, value)
    series.tmdb_id = int(tmdb_id)
    series.metadata_source = "tmdb"
    series.demo_owned = bool(series.demo_owned or demo_owned)
    series.demo_seed_version = seed_version if demo_owned else (series.demo_seed_version or "")
    series.imported_at = series.imported_at or utcnow()
    series.metadata_updated_at = utcnow()
    if created:
        series.slug = _ensure_unique_slug(db, Series, series.title, int(tmdb_id), None)
        series.status = "draft"
    series.genre_links = _ensure_genres(db, details)
    _apply_trailer(series, trailer)

    artwork_files: list[str] = []
    warnings: list[str] = []
    if download_images:
        urls, artwork_files, warnings = _store_artwork(
            settings, details=details, media_type="series", tmdb_configuration=config
        )
        for field, url in urls.items():
            setattr(series, field, url)

    db.add(series)
    db.flush()

    season_ids: list[int] = []
    episode_ids: list[int] = []
    season_items = [s for s in (details.get("seasons") or []) if isinstance(s, dict) and int(s.get("season_number") or 0) > 0]
    season_items.sort(key=lambda s: int(s.get("season_number") or 0))
    if seasons_limit is not None:
        season_items = season_items[: max(0, seasons_limit)]
    now = utcnow()
    for season_item in season_items:
        season_number = int(season_item.get("season_number") or 0)
        season_details = client.season_details(int(tmdb_id), season_number)
        season = (
            db.query(Season)
            .filter(Season.series_id == series.id, Season.season_number == season_number)
            .one_or_none()
        )
        if season is None:
            season = Season(series_id=series.id, season_number=season_number, status="draft")
            db.add(season)
            db.flush()
        season.title = _season_name(season_number, season_details)
        season.description = str(season_details.get("overview") or "")
        season.poster_url = series.poster_url or ""
        season.release_year = _year(season_details.get("air_date"))
        season_ids.append(season.id)
        db.add(season)

        episodes = [e for e in (season_details.get("episodes") or []) if isinstance(e, dict)]
        episodes.sort(key=lambda e: int(e.get("episode_number") or 0))
        if episodes_per_season is not None:
            episodes = episodes[: max(0, episodes_per_season)]
        for item in episodes:
            episode_number = int(item.get("episode_number") or 0)
            if episode_number <= 0:
                continue
            tmdb_episode_id = item.get("id")
            episode = (
                db.query(Episode)
                .filter(Episode.series_id == series.id, Episode.tmdb_id == tmdb_episode_id)
                .one_or_none()
                if tmdb_episode_id
                else None
            )
            if episode is None:
                episode = (
                    db.query(Episode)
                    .filter(Episode.season_id == season.id, Episode.episode_number == episode_number)
                    .one_or_none()
                )
            if episode is None:
                episode = Episode(
                    season_id=season.id,
                    series_id=series.id,
                    episode_number=episode_number,
                    title=str(item.get("name") or f"Episode {episode_number}"),
                    status="draft",
                )
                db.add(episode)
                db.flush()
            episode.season_id = season.id
            episode.series_id = series.id
            episode.episode_number = episode_number
            episode.tmdb_id = int(tmdb_episode_id) if tmdb_episode_id else None
            episode.metadata_source = "tmdb"
            episode.demo_owned = bool(episode.demo_owned or demo_owned)
            episode.demo_seed_version = seed_version if demo_owned else (episode.demo_seed_version or "")
            episode.imported_at = episode.imported_at or now
            episode.metadata_updated_at = now
            episode.title = str(item.get("name") or f"Episode {episode_number}")
            episode.description = str(item.get("overview") or "")
            episode.duration_minutes = int(item.get("runtime") or 0) or None
            episode.release_date = _parse_date(item.get("air_date"))
            episode.thumbnail_url = series.backdrop_url or series.poster_url or ""
            still_path = item.get("still_path")
            if download_images and still_path and tmdb_episode_id:
                still = _store_episode_still(
                    settings,
                    still_path=str(still_path),
                    tmdb_episode_id=int(tmdb_episode_id),
                    tmdb_configuration=config,
                )
                if still is not None:
                    episode.thumbnail_url = still[0]
                    artwork_files.append(still[1])
            db.add(episode)
            episode_ids.append(episode.id)

    db.flush()
    return ImportResult(
        "series",
        series.id,
        int(tmdb_id),
        created=created,
        artwork_files=artwork_files,
        season_ids=season_ids,
        episode_ids=episode_ids,
        warnings=warnings,
    )


def refresh_demo_metadata(
    db: Session,
    settings: Settings,
    *,
    client: TMDBClient | None = None,
    force: bool = False,
) -> list[ImportResult]:
    """Refresh demo-owned TMDB metadata without expanding beyond curated season/episode caps."""
    from app.services.tmdb.curated import CURATED_SERIES

    curated_series = {item.tmdb_id: item for item in CURATED_SERIES}
    results: list[ImportResult] = []
    client = client or TMDBClient(settings)
    for movie in db.query(Movie).filter(Movie.metadata_source == "tmdb", Movie.demo_owned.is_(True), Movie.tmdb_id.isnot(None)).all():
        tmdb_id = movie.tmdb_id
        if tmdb_id is None:
            continue
        results.append(
            import_movie(
                db,
                settings,
                tmdb_id,
                client=client,
                demo_owned=True,
                seed_version=movie.demo_seed_version,
                force=force,
            )
        )
    for series in db.query(Series).filter(Series.metadata_source == "tmdb", Series.demo_owned.is_(True), Series.tmdb_id.isnot(None)).all():
        tmdb_id = series.tmdb_id
        if tmdb_id is None:
            continue
        curated = curated_series.get(int(tmdb_id))
        seasons_limit = curated.seasons if curated is not None else 2
        episodes_per_season = curated.episodes_per_season if curated is not None else 3
        results.append(
            import_series(
                db,
                settings,
                tmdb_id,
                client=client,
                demo_owned=True,
                seed_version=series.demo_seed_version,
                force=force,
                seasons_limit=seasons_limit,
                episodes_per_season=episodes_per_season,
            )
        )
    return results


def preview_movie(settings: Settings, tmdb_id: int, *, client: TMDBClient | None = None) -> dict[str, Any]:
    client = client or TMDBClient(settings)
    details = client.movie_details(int(tmdb_id))
    return {**details, "selected_trailer": select_trailer(client.movie_videos(int(tmdb_id)), language=settings.tmdb_language)}


def preview_series(settings: Settings, tmdb_id: int, *, client: TMDBClient | None = None) -> dict[str, Any]:
    client = client or TMDBClient(settings)
    details = client.tv_details(int(tmdb_id))
    return {**details, "selected_trailer": select_trailer(client.tv_videos(int(tmdb_id)), language=settings.tmdb_language)}
