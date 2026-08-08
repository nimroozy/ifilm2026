"""Catalog domain services: queries, publishing rules, serialization."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.content import Episode, Genre, Movie, Season, Series
from app.models.enums import SORT_OPTIONS
from app.schemas.content import (
    AudioAvailabilityOut,
    EpisodeOut,
    GenreOut,
    MovieOut,
    SeasonOut,
    SeriesOut,
    SubtitleAvailabilityOut,
)
from app.services.catalog_availability import (
    availability_for_episode,
    availability_for_movie,
    availability_for_series,
)
from app.services.publishing.readiness import evaluate_playable_package
from app.services.publishing.visibility import (
    apply_public_visibility,
    public_episode_count_for_season,
    public_episode_count_for_series,
    public_season_count,
)
from app.utils.slug import slug_or_from_title


def utcnow() -> datetime:
    return datetime.now(UTC)


def content_playability(
    db: Session | None, *, movie_id: int | None = None, episode_id: int | None = None
) -> tuple[bool, bool, bool]:
    """Return (playable, has_playable_package, has_external_media).

    Option A: validated primary external counts as has_external_media, but public
    ``playable`` is true for external only when the linked catalog item is demo-owned.
    Packaged HLS remains fully playable for production.
    """
    if db is None:
        return False, False, False
    playable_pkg, _package_id, package_status, _issues = evaluate_playable_package(
        db, movie_id=movie_id, episode_id=episode_id
    )
    has_external = package_status == "external" and playable_pkg
    has_package = playable_pkg and not has_external
    if has_package:
        return True, True, False
    if has_external:
        demo = False
        if movie_id is not None:
            from app.models.content import Movie

            movie = db.get(Movie, movie_id)
            demo = bool(movie and getattr(movie, "demo_owned", False))
        elif episode_id is not None:
            from app.models.content import Episode, Series

            episode = db.get(Episode, episode_id)
            demo = bool(episode and getattr(episode, "demo_owned", False))
            if not demo and episode and episode.series_id:
                series = db.get(Series, episode.series_id)
                demo = bool(series and getattr(series, "demo_owned", False))
        return demo, False, True
    return False, False, False


def not_deleted(query, model):
    return query.filter(model.deleted_at.is_(None))


def genre_out(genre: Genre, *, movie_count: int | None = None, series_count: int | None = None) -> GenreOut:
    return GenreOut(
        id=genre.id,
        name=genre.name,
        slug=genre.slug,
        description=genre.description or "",
        movie_count=movie_count if movie_count is not None else len([m for m in (genre.movies or []) if m.deleted_at is None]),
        series_count=series_count
        if series_count is not None
        else len([s for s in (genre.series or []) if s.deleted_at is None]),
        created_at=genre.created_at,
        updated_at=genre.updated_at,
    )


def movie_out(
    movie: Movie, db: Session | None = None, *, locale: str | None = None
) -> MovieOut:
    from app.schemas.content import CastCreditOut, LocalizationSourcesOut
    from app.services.content_i18n import localized_movie_fields, normalize_locale
    from app.services.tmdb.credits import list_movie_credits

    genres = [genre_out(g, movie_count=0, series_count=0) for g in (movie.genre_links or [])]
    playable, has_package, has_external = content_playability(db, movie_id=movie.id)
    audio_av, sub_av = availability_for_movie(
        movie,
        db,
        has_playable_package=has_package,
        has_external_media=has_external,
    )
    credits_out: list[CastCreditOut] = []
    if db is not None:
        for row in list_movie_credits(db, movie.id):
            credits_out.append(
                CastCreditOut(
                    person_id=row.tmdb_person_id,
                    name=row.name,
                    character=row.character_name or "",
                    profile_path=row.profile_path or "",
                    profile_url=row.profile_url or "",
                    order=row.credit_order,
                )
            )
    loc = normalize_locale(locale)
    title = movie.title
    description = movie.description or ""
    short_description = movie.short_description or ""
    tagline = ""
    localization = None
    if db is not None:
        localized = localized_movie_fields(db, movie, loc)
        title = localized["title"]
        description = localized["description"]
        short_description = localized["short_description"]
        tagline = localized.get("tagline") or ""
        localization = LocalizationSourcesOut.model_validate(localized["localization"])
    return MovieOut(
        id=movie.id,
        title=title,
        original_title=movie.original_title or "",
        slug=movie.slug,
        description=description,
        short_description=short_description,
        tagline=tagline,
        localization=localization,
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
        trailer_url=movie.trailer_url or "",
        spoken_languages=getattr(movie, "spoken_languages", None) or [],
        trailer_provider=getattr(movie, "trailer_provider", "") or "",
        trailer_key=getattr(movie, "trailer_key", "") or "",
        trailer_title=getattr(movie, "trailer_title", "") or "",
        trailer_official=bool(getattr(movie, "trailer_official", False)),
        trailer_language=getattr(movie, "trailer_language", "") or "",
        trailer_published_at=getattr(movie, "trailer_published_at", None),
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
        producer=getattr(movie, "producer", "") or "",
        writer=getattr(movie, "writer", "") or "",
        studio=getattr(movie, "studio", "") or "",
        cast=movie.cast or [],
        credits=credits_out,
        credits_synced_at=getattr(movie, "credits_synced_at", None),
        audio=movie.audio or [],
        subtitles=movie.subtitles or [],
        qualities=movie.qualities or [],
        dubbed=movie.dubbed or [],
        audio_availability=AudioAvailabilityOut.model_validate(audio_av.model_dump()),
        subtitle_availability=SubtitleAvailabilityOut.model_validate(sub_av.model_dump()),
        views=movie.views or 0,
        type="movie",
        hls_path=movie.hls_path,
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


def series_out(
    series: Series,
    *,
    public_counts: bool = False,
    db: Session | None = None,
    locale: str | None = None,
) -> SeriesOut:
    from app.schemas.content import LocalizationSourcesOut
    from app.services.content_i18n import localized_series_fields, normalize_locale

    genres = [genre_out(g, movie_count=0, series_count=0) for g in (series.genre_links or [])]
    if public_counts:
        season_count = public_season_count(series)
        episode_count = public_episode_count_for_series(series)
    else:
        seasons = [s for s in (series.seasons or []) if s.deleted_at is None]
        season_count = len(seasons)
        episode_count = sum(len([e for e in (s.episodes or []) if e.deleted_at is None]) for s in seasons)
    audio_av, sub_av = availability_for_series(series, db)
    loc = normalize_locale(locale)
    title = series.title
    description = series.description or ""
    short_description = series.short_description or ""
    tagline = ""
    localization = None
    if db is not None:
        localized = localized_series_fields(db, series, loc)
        title = localized["title"]
        description = localized["description"]
        short_description = localized["short_description"]
        tagline = localized.get("tagline") or ""
        localization = LocalizationSourcesOut.model_validate(localized["localization"])
    return SeriesOut(
        id=series.id,
        title=title,
        original_title=series.original_title or "",
        slug=series.slug,
        description=description,
        short_description=short_description,
        tagline=tagline,
        localization=localization,
        release_year=series.release_year,
        end_year=series.end_year,
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
        trailer_url=series.trailer_url or "",
        spoken_languages=getattr(series, "spoken_languages", None) or [],
        trailer_provider=getattr(series, "trailer_provider", "") or "",
        trailer_key=getattr(series, "trailer_key", "") or "",
        trailer_title=getattr(series, "trailer_title", "") or "",
        trailer_official=bool(getattr(series, "trailer_official", False)),
        trailer_language=getattr(series, "trailer_language", "") or "",
        trailer_published_at=getattr(series, "trailer_published_at", None),
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
        audio=series.audio or [],
        subtitles=series.subtitles or [],
        dubbed=series.dubbed or [],
        audio_availability=AudioAvailabilityOut.model_validate(audio_av.model_dump()),
        subtitle_availability=SubtitleAvailabilityOut.model_validate(sub_av.model_dump()),
        new_episode=bool(series.new_episode),
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


def season_out(season: Season, *, public_counts: bool = False) -> SeasonOut:
    if public_counts:
        episode_count = public_episode_count_for_season(season)
    else:
        episode_count = len([e for e in (season.episodes or []) if e.deleted_at is None])
    return SeasonOut(
        id=season.id,
        series_id=season.series_id,
        season_number=season.season_number,
        title=season.title or "",
        description=season.description or "",
        poster_url=season.poster_url or "",
        release_year=season.release_year,
        status=season.status,
        published_at=getattr(season, "published_at", None),
        scheduled_publish_at=getattr(season, "scheduled_publish_at", None),
        episode_count=episode_count,
        created_at=season.created_at,
        updated_at=season.updated_at,
    )


def episode_out(
    episode: Episode, db: Session | None = None, *, locale: str | None = None
) -> EpisodeOut:
    from app.services.content_i18n import localized_episode_fields, normalize_locale

    playable, has_package, has_external = content_playability(db, episode_id=episode.id)
    series = episode.series if getattr(episode, "series", None) is not None else None
    if series is None and db is not None and episode.series_id:
        series = db.get(Series, episode.series_id)
    audio_av, sub_av = availability_for_episode(episode, db, series=series)
    title = episode.title
    description = episode.description or ""
    if db is not None:
        localized = localized_episode_fields(db, episode, normalize_locale(locale))
        title = localized["title"]
        description = localized["description"]
    return EpisodeOut(
        id=episode.id,
        season_id=episode.season_id,
        series_id=episode.series_id,
        episode_number=episode.episode_number,
        tmdb_id=getattr(episode, "tmdb_id", None),
        metadata_source=getattr(episode, "metadata_source", "") or "",
        demo_owned=bool(getattr(episode, "demo_owned", False)),
        has_demo_clip=bool(getattr(episode, "has_demo_clip", False)),
        title=title,
        description=description,
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
        audio_availability=AudioAvailabilityOut.model_validate(audio_av.model_dump()),
        subtitle_availability=SubtitleAvailabilityOut.model_validate(sub_av.model_dump()),
        season=episode.season.season_number if episode.season else None,
        episode=episode.episode_number,
        duration=episode.duration_minutes,
        thumbnail=episode.thumbnail_url or "",
    )


def load_genres(db: Session, genre_ids: list[int]) -> list[Genre]:
    if not genre_ids:
        return []
    genres = db.query(Genre).filter(Genre.id.in_(genre_ids)).all()
    if len(genres) != len(set(genre_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more genres not found")
    return genres


def ensure_unique_movie_slug(db: Session, slug: str, *, exclude_id: int | None = None) -> None:
    q = not_deleted(db.query(Movie), Movie).filter(Movie.slug == slug)
    if exclude_id is not None:
        q = q.filter(Movie.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Movie slug already exists")


def ensure_unique_series_slug(db: Session, slug: str, *, exclude_id: int | None = None) -> None:
    q = not_deleted(db.query(Series), Series).filter(Series.slug == slug)
    if exclude_id is not None:
        q = q.filter(Series.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Series slug already exists")


def ensure_unique_genre_slug(db: Session, slug: str, *, exclude_id: int | None = None) -> None:
    q = db.query(Genre).filter(Genre.slug == slug)
    if exclude_id is not None:
        q = q.filter(Genre.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Genre slug already exists")


def ensure_unique_imdb(db: Session, model, imdb_id: str | None, *, exclude_id: int | None = None) -> None:
    if not imdb_id:
        return
    q = not_deleted(db.query(model), model).filter(model.imdb_id == imdb_id)
    if exclude_id is not None:
        q = q.filter(model.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="IMDb identifier already exists")


def apply_sort(query, model, sort: str):
    if sort not in SORT_OPTIONS:
        sort = "newest"
    rating_col = getattr(model, "imdb_rating", None)
    if sort == "oldest":
        return query.order_by(model.created_at.asc(), model.id.asc())
    if sort == "title_asc":
        return query.order_by(model.title.asc(), model.id.asc())
    if sort == "title_desc":
        return query.order_by(model.title.desc(), model.id.desc())
    if sort == "rating_desc" and rating_col is not None:
        return query.order_by(rating_col.desc(), model.id.desc())
    if sort == "recently_updated":
        return query.order_by(model.updated_at.desc(), model.id.desc())
    return query.order_by(model.created_at.desc(), model.id.desc())


def filter_catalog_query(
    query,
    model,
    *,
    q: str | None = None,
    genre: str | None = None,
    year: int | None = None,
    language: str | None = None,
    featured: bool | None = None,
    trending: bool | None = None,
    status: str | None = None,
    published_only: bool = False,
):
    query = not_deleted(query, model)
    if published_only:
        query = apply_public_visibility(query, model)
    elif status:
        query = query.filter(model.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(model.title.ilike(like), model.original_title.ilike(like), model.slug.ilike(like)))
    if year is not None:
        query = query.filter(model.release_year == year)
    if language:
        query = query.filter(model.language.ilike(language))
    if featured is not None:
        query = query.filter(model.is_featured.is_(featured))
    if trending is not None:
        query = query.filter(model.is_trending.is_(trending))
    if genre:
        # Use EXISTS (.any) instead of JOIN + DISTINCT. DISTINCT over JSON columns
        # (e.g. movies.cast) fails on PostgreSQL: "could not identify an equality
        # operator for type json".
        genre_match = or_(Genre.slug == genre, Genre.name.ilike(genre))
        if model is Movie:
            query = query.filter(Movie.genre_links.any(genre_match))
        elif model is Series:
            query = query.filter(Series.genre_links.any(genre_match))
    return query


def get_movie(db: Session, movie_id: int, *, include_deleted: bool = False) -> Movie:
    movie = (
        db.query(Movie)
        .options(joinedload(Movie.genre_links))
        .filter(Movie.id == movie_id)
        .first()
    )
    if not movie or (movie.deleted_at is not None and not include_deleted):
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie


def get_series(db: Session, series_id: int, *, include_deleted: bool = False) -> Series:
    series = (
        db.query(Series)
        .options(joinedload(Series.genre_links), joinedload(Series.seasons).joinedload(Season.episodes))
        .filter(Series.id == series_id)
        .first()
    )
    if not series or (series.deleted_at is not None and not include_deleted):
        raise HTTPException(status_code=404, detail="Series not found")
    return series


def resolve_movie(db: Session, id_or_slug: str, *, published_only: bool = False) -> Movie:
    query = db.query(Movie).options(joinedload(Movie.genre_links))
    query = not_deleted(query, Movie)
    if id_or_slug.isdigit():
        query = query.filter(Movie.id == int(id_or_slug))
    else:
        query = query.filter(Movie.slug == id_or_slug)
    if published_only:
        query = apply_public_visibility(query, Movie)
    movie = query.first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie


def resolve_series(db: Session, id_or_slug: str, *, published_only: bool = False) -> Series:
    query = (
        db.query(Series)
        .options(joinedload(Series.genre_links), joinedload(Series.seasons).joinedload(Season.episodes))
    )
    query = not_deleted(query, Series)
    if id_or_slug.isdigit():
        query = query.filter(Series.id == int(id_or_slug))
    else:
        query = query.filter(Series.slug == id_or_slug)
    if published_only:
        query = apply_public_visibility(query, Series)
    series = query.first()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    return series


def soft_delete(entity) -> None:
    """Legacy soft-delete helper — prefer publishing workflow archive()."""
    entity.deleted_at = utcnow()
    entity.status = "archived"
    entity.archived_at = getattr(entity, "archived_at", None) or utcnow()


def publish_entity(entity) -> None:
    """Legacy helper retained for bootstrap/tests — prefer workflow.publish()."""
    entity.status = "published"
    entity.published_at = entity.published_at or utcnow()
    entity.deleted_at = None


def unpublish_entity(entity) -> None:
    """Legacy helper — prefer workflow.unpublish() (sets unpublished, not draft)."""
    entity.status = "unpublished"
    entity.unpublished_at = utcnow()
    entity.scheduled_publish_at = None


def publish_episode(db: Session, episode: Episode) -> Episode:
    """Legacy episode publish — prefer workflow; parents need not be published for status,
    but public visibility still requires the chain (see visibility.episode_is_public)."""
    season = db.get(Season, episode.season_id)
    if not season or season.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Cannot publish episode without a season")
    series = db.get(Series, episode.series_id)
    if not series or series.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Cannot publish episode without a series")
    if season.status == "archived" or series.status == "archived":
        raise HTTPException(status_code=400, detail="Cannot publish episode under archived parent")
    publish_entity(episode)
    return episode


def make_slug_for_movie(db: Session, title: str, slug: str | None, *, exclude_id: int | None = None) -> str:
    try:
        candidate = slug_or_from_title(slug, title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ensure_unique_movie_slug(db, candidate, exclude_id=exclude_id)
    return candidate


def make_slug_for_series(db: Session, title: str, slug: str | None, *, exclude_id: int | None = None) -> str:
    try:
        candidate = slug_or_from_title(slug, title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ensure_unique_series_slug(db, candidate, exclude_id=exclude_id)
    return candidate
